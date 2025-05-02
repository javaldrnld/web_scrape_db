import re
import urllib3
import requests
from bs4 import BeautifulSoup, Tag, Comment
import time
import logging
import os
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# Configure logging
def setup_logger():
    if not os.path.exists('logs'):
        os.makedirs('logs')
    logger = logging.getLogger('earthquake_scraperv')
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/earthquake_scraper_{timestamp}.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s')
    console_handler.setFormatter(console_format)
    file_handler.setFormatter(file_format)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger

logger = setup_logger()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constants
BASE_URL = "https://earthquake.phivolcs.dost.gov.ph/"
REQUEST_DELAY = 0.5  # seconds between requests
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://mongodb:27017/scraper_db')
DB_NAME = 'scraper_db'
COLLECTION_NAME = 'earthquakes'

# Initialize MongoDB client
try:
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    client.server_info()
    logger.info(f"Successfully connected to MongoDB at {MONGODB_URI}")
except ConnectionFailure as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise

logger.info(f"Starting earthquake data scraper for {BASE_URL}")

# Fetch main page
try:
    response = requests.get(BASE_URL, verify=False)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    logger.info(f"Successfully fetched main page: {BASE_URL} (Status: {response.status_code})")
except requests.exceptions.RequestException as e:
    logger.error(f"Failed to fetch main page: {e}")
    raise

def extract_comment_block(soup, comment_text):
    logger.debug(f"Searching for comment block: '{comment_text}'")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if comment_text in comment:
            parent = comment.parent
            logger.debug(f"Found comment block: '{comment_text}'")
            return parent
    logger.warning(f"Comment block '{comment_text}' not found")
    return None

def parse_datetime(date_str, time_str):
    try:
        datetime_str = f"{date_str.strip()} {time_str.strip()}"
        if 'AM' in time_str or 'PM' in time_str:
            try:
                return datetime.strptime(datetime_str, "%d %b %Y %I:%M:%S %p")
            except ValueError:
                try:
                    return datetime.strptime(datetime_str, "%d %b %Y %I:%M %p")
                except ValueError:
                    try:
                        return datetime.strptime(datetime_str, "%d %B %Y %I:%M:%S %p")
                    except ValueError:
                        return datetime.strptime(datetime_str, "%d %B %Y %I:%M %p")
        else:
            try:
                return datetime.strptime(datetime_str, "%d %b %Y %H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(datetime_str, "%d %b %Y %H:%M")
                except ValueError:
                    try:
                        return datetime.strptime(datetime_str, "%d %B %Y %H:%M:%S")
                    except ValueError:
                        return datetime.strptime(datetime_str, "%d %B %Y %H:%M")
    except ValueError as e:
        logger.error(f"Failed to parse datetime '{datetime_str}': {e}")
        return None

def parse_coordinate(coord_str):
    try:
        match = re.search(r'(\d+\.\d+)', coord_str)
        if not match:
            logger.warning(f"Invalid coordinate format: {coord_str}")
            return None
        value = float(match.group(1))
        if 'S' in coord_str or 'W' in coord_str:
            value = -value
        return value
    except ValueError as e:
        logger.error(f"Failed to parse coordinate '{coord_str}': {e}")
        return None

def parse_magnitude(magnitude_str):
    try:
        match = re.search(r'([A-Za-z]+)\s+(\d+\.\d+)', magnitude_str)
        if match:
            mag_type = match.group(1)
            mag_value = float(match.group(2))
            return mag_type, mag_value
        else:
            logger.warning(f"Invalid magnitude format: {magnitude_str}")
            return None, None
    except ValueError as e:
        logger.error(f"Failed to parse magnitude '{magnitude_str}': {e}")
        return None, None

def get_base_filename(filename):
    """Extract base filename by removing any suffix like _B2 and .html"""
    if not filename:
        return None
    # Remove any suffix like _B2, _B1, _A1, etc., and .html
    base = re.sub(r'_[A-Z]\d*\.html$', '', filename)
    return base

def extract_monthly_earthquake_data(soup, url):
    logger.info(f"Extracting earthquake data from: {url}")
    results = []
    try:
        tbodies = soup.find_all("tbody")
        logger.debug(f"Total <tbody> elements found: {len(tbodies)}")
        if len(tbodies) < 3:
            logger.error(f"Required tbody not found (expected at least 3, found {len(tbodies)})")
            return results
        tbody = tbodies[2]
        trs = tbody.contents
        if len(trs) < 3:
            logger.warning(f"Not enough rows in tbody (found {len(trs)})")
            return results
        current_node = trs[2].next_sibling
        event_count = 0
        while current_node:
            if "end of last event" in str(current_node):
                logger.debug("Reached end of events marker")
                break
            if isinstance(current_node, Tag):
                links = current_node.find("a", href=True)
                if links:
                    href = links["href"].replace("\\", "/")
                    full_url = BASE_URL + href
                    logger.debug(f"Processing earthquake event: {full_url}")
                    try:
                        inner_response = requests.get(full_url, verify=False)
                        inner_response.raise_for_status()
                        inner_soup = BeautifulSoup(inner_response.content, "html.parser")
                        logger.debug(f"Successfully fetched event data (Status: {inner_response.status_code})")
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Failed to fetch event data: {e}")
                        current_node = current_node.next_sibling
                        time.sleep(REQUEST_DELAY)
                        continue
                    earthquake_info = {}
                    # EQ Number
                    try:
                        eq_block = extract_comment_block(inner_soup, "1 EQInfo-Data").get_text(strip=True)
                        match = re.search(r'NO\. *: *(\d+)', eq_block)
                        if match:
                            eq_no = int(match.group(1))
                            earthquake_info["eq_no"] = eq_no
                            logger.debug(f"Extracted EQ number: {eq_no}")
                        else:
                            earthquake_info["eq_no"] = None
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting EQ number: {e}")
                        earthquake_info["eq_no"] = None
                    # Date and Time
                    try:
                        datetime_block = extract_comment_block(inner_soup, "2 DateTime-Data").get_text(strip=True)
                        date, dt_time = datetime_block.split("-")
                        earthquake_info["date_str"] = date.strip()
                        earthquake_info["time_str"] = dt_time.strip()
                        earthquake_info["datetime"] = parse_datetime(date.strip(), dt_time.strip())
                        logger.debug(f"Extracted datetime: {earthquake_info['datetime']}")
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting date/time: {e}")
                        earthquake_info["date_str"] = ""
                        earthquake_info["time_str"] = ""
                        earthquake_info["datetime"] = None
                    # Location
                    try:
                        location_block = extract_comment_block(inner_soup, "3 Location-Data").get_text(strip=True)
                        lat_lon = re.findall(r"\d+\.\d+°[A-Z]", location_block)
                        if len(lat_lon) >= 2:
                            lat_str, lon_str = lat_lon[0], lat_lon[1]
                            earthquake_info["latitude_str"] = lat_str.strip()
                            earthquake_info["longitude_str"] = lon_str.strip()
                            earthquake_info["latitude"] = parse_coordinate(lat_str)
                            earthquake_info["longitude"] = parse_coordinate(lon_str)
                            logger.debug(f"Extracted coordinates: {earthquake_info['latitude']}, {earthquake_info['longitude']}")
                        else:
                            earthquake_info["latitude_str"] = ""
                            earthquake_info["longitude_str"] = ""
                            earthquake_info["latitude"] = None
                            earthquake_info["longitude"] = None
                        region_match = re.findall(r"(\d{3}\s+.*)", location_block)
                        if region_match:
                            region = region_match[0].strip()
                            earthquake_info["region"] = region
                            logger.debug(f"Extracted region: {region}")
                        else:
                            earthquake_info["region"] = ""
                    except AttributeError as e:
                        logger.error(f"Error extracting location: {e}")
                        earthquake_info["latitude_str"] = ""
                        earthquake_info["longitude_str"] = ""
                        earthquake_info["latitude"] = None
                        earthquake_info["longitude"] = None
                        earthquake_info["region"] = ""
                    # Depth
                    try:
                        depth_str = extract_comment_block(inner_soup, "4 Depth-Data").get_text(strip=True)
                        earthquake_info["depth_str"] = depth_str.strip()
                        depth_match = re.search(r'(\d+)', depth_str)
                        if depth_match:
                            earthquake_info["depth_km"] = int(depth_match.group(1))
                            logger.debug(f"Extracted depth: {earthquake_info['depth_km']} km")
                        else:
                            earthquake_info["depth_km"] = None
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting depth: {e}")
                        earthquake_info["depth_str"] = ""
                        earthquake_info["depth_km"] = None
                    # Origin
                    try:
                        origin = extract_comment_block(inner_soup, "5 Origin-Data").get_text(strip=True)
                        earthquake_info["origin"] = origin.strip()
                        logger.debug(f"Extracted origin: {origin.strip()}")
                    except AttributeError as e:
                        logger.error(f"Error extracting origin: {e}")
                        earthquake_info["origin"] = ""
                    # Magnitude
                    try:
                        magnitude_str = extract_comment_block(inner_soup, "6 Magnitude-Data").get_text(strip=True)
                        earthquake_info["magnitude_str"] = magnitude_str.strip()
                        mag_type, mag_value = parse_magnitude(magnitude_str)
                        earthquake_info["magnitude_type"] = mag_type
                        earthquake_info["magnitude_value"] = mag_value
                        logger.debug(f"Extracted magnitude: type={mag_type}, value={mag_value}")
                    except AttributeError as e:
                        logger.error(f"Error extracting magnitude: {e}")
                        earthquake_info["magnitude_str"] = ""
                        earthquake_info["magnitude_type"] = None
                        earthquake_info["magnitude_value"] = None
                    # Map Image (Filename)
                    try:
                        filename = extract_comment_block(inner_soup, "8 Map-Data")
                        img_tag = filename.find("img")
                        src = img_tag.get("src").strip()[:-4]
                        earthquake_info["filename"] = src
                        earthquake_info["base_filename"] = get_base_filename(src)
                        logger.debug(f"Extracted map filename: {src}, base_filename: {earthquake_info['base_filename']}")
                    except AttributeError as e:
                        logger.error(f"Error extracting map filename: {e}")
                        earthquake_info["filename"] = ""
                        earthquake_info["base_filename"] = ""
                    # Intensities
                    try:
                        reported_block = extract_comment_block(inner_soup, "7 Intensity-Data")
                        reported_txt = reported_block.decode_contents().replace("<br/>", "\n")
                        reported_txt = BeautifulSoup(reported_txt, "html.parser").get_text(separator="\n")
                        reported_txt = re.sub(r"(Intensity)", r" \1", reported_txt)
                        reported_intensities = []
                        instrumental_intensities = []
                        if "Instrumental Intensities:" in reported_txt:
                            reported_part, instrumental_part = reported_txt.split("Instrumental Intensities:")
                        else:
                            reported_part = reported_txt
                            instrumental_part = ""
                        pattern = r"Intensity\s+([IVXLCDM]+)\s*-?\s*(.+?)(?=\n|$)"
                        reported_intensity_matches = re.findall(pattern, reported_part)
                        for intensity, location in reported_intensity_matches:
                            reported_intensities.append({
                                "intensity": intensity,
                                "locations": location.strip()
                            })
                        instrumental_intensity_matches = re.findall(pattern, instrumental_part)
                        for intensity, location in instrumental_intensity_matches:
                            instrumental_intensities.append({
                                "intensity": intensity,
                                "locations": location.strip()
                            })
                        earthquake_info["reported_intensities"] = reported_intensities
                        earthquake_info["instrumental_intensities"] = instrumental_intensities
                        logger.debug(f"Extracted {len(reported_intensities)} reported and {len(instrumental_intensities)} instrumental intensities")
                    except AttributeError as e:
                        logger.error(f"Error extracting intensities: {e}")
                        earthquake_info["reported_intensities"] = []
                        earthquake_info["instrumental_intensities"] = []
                    # Issued Date/Time
                    try:
                        issued_block = extract_comment_block(inner_soup, "10 IssuedDT-Data").get_text(strip=True)
                        issued_date, issued_time = issued_block.split("-")
                        earthquake_info["issued_date_str"] = issued_date.strip()
                        earthquake_info["issued_time_str"] = issued_time.strip()
                        earthquake_info["issued_datetime"] = parse_datetime(issued_date.strip(), issued_time.strip())
                        logger.debug(f"Extracted issued datetime: {earthquake_info['issued_datetime']}")
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting issued date/time: {e}")
                        earthquake_info["issued_date_str"] = ""
                        earthquake_info["issued_time_str"] = ""
                        earthquake_info["issued_datetime"] = None
                    # Authors
                    try:
                        prepared_block = extract_comment_block(inner_soup, "11 PreparedBy-Data").get_text(strip=True)
                        authors = prepared_block.split("/")
                        authors_dict = {}
                        for i, author in enumerate(authors, start=1):
                            authors_dict[f"auth_{i}"] = author.strip()
                        earthquake_info["authors"] = authors_dict
                        logger.debug(f"Extracted {len(authors)} authors")
                    except AttributeError as e:
                        logger.error(f"Error extracting authors: {e}")
                        earthquake_info["authors"] = {}
                    results.append(earthquake_info)
                    event_count += 1
                    logger.info(f"Successfully processed earthquake #{earthquake_info.get('eq_no', 'unknown')} - {earthquake_info.get('datetime', 'unknown')}")
            current_node = current_node.next_sibling
            time.sleep(REQUEST_DELAY)
        logger.info(f"Completed extraction with {event_count} events")
        return results
    except Exception as e:
        logger.exception(f"Unexpected error during extraction: {e}")
        return results

# Main execution
try:
    logger.info("Extracting current month earthquake data")
    new_data = extract_monthly_earthquake_data(soup, BASE_URL)
    logger.info(f"Extracted {len(new_data)} earthquake events")
    
    # Process data according to flowchart
    updated_count = 0
    inserted_count = 0
    kept_count = 0
    
    for event in new_data:
        filename = event.get("filename")
        base_filename = event.get("base_filename")
        if not base_filename:
            logger.warning(f"Skipping event with no valid filename: EQ #{event.get('eq_no', 'unknown')}")
            continue
        # Check if event exists in MongoDB by base_filename
        existing_event = collection.find_one({"base_filename": base_filename})
        if existing_event:
            existing_issued = existing_event.get("issued_datetime")
            new_issued = event.get("issued_datetime")
            if existing_issued and new_issued:
                if existing_issued == new_issued:
                    logger.debug(f"Keeping existing event for base_filename {base_filename} (issued time unchanged)")
                    kept_count += 1
                    continue
                else:
                    logger.info(f"Updating event for base_filename {base_filename} (issued time changed, new filename: {filename})")
                    try:
                        collection.replace_one({"base_filename": base_filename}, event)
                        updated_count += 1
                    except OperationFailure as e:
                        logger.error(f"Failed to update event for base_filename {base_filename}: {e}")
            else:
                logger.info(f"Updating event for base_filename {base_filename} (missing issued time, new filename: {filename})")
                try:
                    collection.replace_one({"base_filename": base_filename}, event)
                    updated_count += 1
                except OperationFailure as e:
                    logger.error(f"Failed to update event for base_filename {base_filename}: {e}")
        else:
            logger.info(f"Inserting new event for base_filename {base_filename} (filename: {filename})")
            try:
                collection.insert_one(event)
                inserted_count += 1
            except OperationFailure as e:
                logger.error(f"Failed to insert event for base_filename {base_filename}: {e}")
    
    logger.info(f"Processing complete: {inserted_count} inserted, {updated_count} updated, {kept_count} kept")
    
except Exception as e:
    logger.exception(f"Script execution failed with error: {e}")
    raise
finally:
    client.close()
    logger.info("Closed MongoDB connection")

logger.info("Script execution completed")