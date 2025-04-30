import re
import urllib3
from urllib.parse import urljoin
import pprint
import polars as pl
import requests
from bs4 import BeautifulSoup, NavigableString, Tag, Comment
import time
import logging
import os
from datetime import datetime


# Configure logging
def setup_logger():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    # Create a logger
    logger = logging.getLogger('earthquake_scraper')
    logger.setLevel(logging.DEBUG)
    
    # Create console handler with a higher log level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create file handler which logs even debug messages
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/earthquake_scraper_{timestamp}.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    # Create formatters and add them to handlers
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s')
    console_handler.setFormatter(console_format)
    file_handler.setFormatter(file_format)
    
    # Add the handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Initialize logger
logger = setup_logger()

# Disable warnings for insecure requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constants
BASE_URL = "https://earthquake.phivolcs.dost.gov.ph/"
REQUEST_DELAY = 0.5  # seconds between requests

logger.info(f"Starting earthquake data scraper for {BASE_URL}")

try:
    response = requests.get(BASE_URL, verify=False)
    response.raise_for_status()  # Raise exception for bad status codes
    soup = BeautifulSoup(response.content, "html.parser")
    logger.info(f"Successfully fetched main page: {BASE_URL} (Status: {response.status_code})")
except requests.exceptions.RequestException as e:
    logger.error(f"Failed to fetch main page: {e}")
    raise


def extract_comment_block(soup, comment_text):
    """Extract HTML block after a specific comment"""
    logger.debug(f"Searching for comment block: '{comment_text}'")
    
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if comment_text in comment:
            # get the parent element containing this comment
            parent = comment.parent
            logger.debug(f"Found comment block: '{comment_text}'")
            # return parent only since its only needed and strip the text
            return parent
    
    logger.warning(f"Comment block '{comment_text}' not found")
    return None

def parse_datetime(date_str, time_str):
    """Convert date and time strings to datetime object"""
    try:
        # Combine date and time
        datetime_str = f"{date_str.strip()} {time_str.strip()}"
        
        # Handle AM/PM formats (12-hour)
        if 'AM' in time_str or 'PM' in time_str:
            try:
                # Try 12-hour format with seconds (allow abbreviated month names)
                return datetime.strptime(datetime_str, "%d %b %Y %I:%M:%S %p")
            except ValueError:
                # Fallback to 12-hour format without seconds
                return datetime.strptime(datetime_str, "%d %b %Y %I:%M %p")
        else:
            try:
                # Try 24-hour format with seconds
                return datetime.strptime(datetime_str, "%d %b %Y %H:%M:%S")
            except ValueError:
                # Fallback to 24-hour format without seconds
                return datetime.strptime(datetime_str, "%d %b %Y %H:%M")
    except ValueError as e:
        logger.error(f"Failed to parse datetime '{datetime_str}': {e}")
        return None
    
def parse_coordinate(coord_str):
    """Convert coordinate string (e.g., '14.99°N') to float"""
    try:
        # Extract numeric part
        match = re.search(r'(\d+\.\d+)', coord_str)
        if not match:
            logger.warning(f"Invalid coordinate format: {coord_str}")
            return None
        
        value = float(match.group(1))
        
        # Adjust for direction
        if 'S' in coord_str or 'W' in coord_str:
            value = -value
            
        return value
    except ValueError as e:
        logger.error(f"Failed to parse coordinate '{coord_str}': {e}")
        return None


def parse_magnitude(magnitude_str):
    """Extract magnitude type and value from string (e.g., 'Ms 1.8')"""
    try:
        # Use regex to separate type and value
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


def extract_monthly_earthquake_data(soup, url_month):
    """Extract earthquake data from monthly page"""
    logger.info(f"Extracting earthquake data from: {url_month}")
    
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
                    
                    # Extract EQ Number - convert to int
                    try:
                        eq_block = extract_comment_block(inner_soup, "1 EQInfo-Data").get_text(strip=True)
                        match = re.search(r'NO\. *: *(\d+)', eq_block)
                        if match:
                            eq_no = int(match.group(1))
                            earthquake_info["eq_no"] = eq_no
                            logger.debug(f"Extracted EQ number: {eq_no}")
                        else:
                            logger.warning(f"No EQ number pattern found in: {eq_block}")
                            earthquake_info["eq_no"] = None
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting EQ number: {e}")
                        earthquake_info["eq_no"] = None

                    # Extract Date and Time - combine and convert to datetime
                    try:
                        datetime_block = extract_comment_block(inner_soup, "2 DateTime-Data").get_text(strip=True)
                        date, dt_time = datetime_block.split("-")
                        # Store original string data
                        earthquake_info["date_str"] = date.strip()
                        earthquake_info["time_str"] = dt_time.strip()
                        # Convert to datetime object
                        earthquake_info["datetime"] = parse_datetime(date.strip(), dt_time.strip())
                        logger.debug(f"Extracted datetime: {earthquake_info['datetime']}")
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting date/time: {e}")
                        earthquake_info["date_str"] = ""
                        earthquake_info["time_str"] = ""
                        earthquake_info["datetime"] = None

                    # Extract Location - convert lat/lon to float
                    try:
                        location_block = extract_comment_block(inner_soup, "3 Location-Data").get_text(strip=True)
                        lat_lon = re.findall(r"\d+\.\d+°[A-Z]", location_block)
                        if len(lat_lon) >= 2:
                            lat_str, lon_str = lat_lon[0], lat_lon[1]
                            # Store original string data
                            earthquake_info["latitude_str"] = lat_str.strip()
                            earthquake_info["longitude_str"] = lon_str.strip()
                            # Convert to float
                            earthquake_info["latitude"] = parse_coordinate(lat_str)
                            earthquake_info["longitude"] = parse_coordinate(lon_str)
                            logger.debug(f"Extracted coordinates: {earthquake_info['latitude']}, {earthquake_info['longitude']}")
                        else:
                            logger.warning(f"Coordinates not found in: {location_block}")
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
                            logger.warning(f"Region not found in: {location_block}")
                            earthquake_info["region"] = ""
                    except AttributeError as e:
                        logger.error(f"Error extracting location: {e}")
                        earthquake_info["latitude_str"] = ""
                        earthquake_info["longitude_str"] = ""
                        earthquake_info["latitude"] = None
                        earthquake_info["longitude"] = None
                        earthquake_info["region"] = ""

                    # Extract Depth - convert to int
                    try:
                        depth_str = extract_comment_block(inner_soup, "4 Depth-Data").get_text(strip=True)
                        earthquake_info["depth_str"] = depth_str.strip()
                        # Extract numeric part and convert to int
                        depth_match = re.search(r'(\d+)', depth_str)
                        if depth_match:
                            earthquake_info["depth_km"] = int(depth_match.group(1))
                            logger.debug(f"Extracted depth: {earthquake_info['depth_km']} km")
                        else:
                            logger.warning(f"Could not extract numeric depth from: {depth_str}")
                            earthquake_info["depth_km"] = None
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting depth: {e}")
                        earthquake_info["depth_str"] = ""
                        earthquake_info["depth_km"] = None

                    # Extract Origin
                    try:
                        origin = extract_comment_block(inner_soup, "5 Origin-Data").get_text(strip=True)
                        earthquake_info["origin"] = origin.strip()
                        logger.debug(f"Extracted origin: {origin.strip()}")
                    except AttributeError as e:
                        logger.error(f"Error extracting origin: {e}")
                        earthquake_info["origin"] = ""

                    # Extract Magnitude - separate type and value
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

                    # Extract Map Image
                    try:
                        filename = extract_comment_block(inner_soup, "8 Map-Data")
                        img_tag = filename.find("img")
                        src = img_tag.get("src").strip()[:-4]
                        earthquake_info["filename"] = src
                        logger.debug(f"Extracted map filename: {src}")
                    except AttributeError as e:
                        logger.error(f"Error extracting map filename: {e}")
                        earthquake_info["filename"] = ""

                    # Extract Intensities
                    try:
                        reported_block = extract_comment_block(inner_soup, "7 Intensity-Data")
                        reported_txt = reported_block.decode_contents().replace("<br/>", "\n")
                        reported_txt = BeautifulSoup(reported_txt, "html.parser").get_text(separator="\n")
                        reported_txt = re.sub(r"(Intensity)", r" \1", reported_txt)
                        
                        # Initialize lists
                        reported_intensities = []
                        instrumental_intensities = []

                        # Check if there are Instrumental Intensities
                        if "Instrumental Intensities:" in reported_txt:
                            reported_part, instrumental_part = reported_txt.split("Instrumental Intensities:")
                        else:
                            reported_part = reported_txt
                            instrumental_part = ""

                        # Pattern to extract: e.g., "Intensity IV - Some Location"
                        pattern = r"Intensity\s+([IVXLCDM]+)\s*-?\s*(.+?)(?=\n|$)"

                        # Reported
                        reported_intensity_matches = re.findall(pattern, reported_part)
                        for intensity, location in reported_intensity_matches:
                            reported_intensities.append({
                                "intensity": intensity,
                                "locations": location.strip()
                            })

                        # Instrumental
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

                    # Extract Issued Date/Time
                    try:
                        issued_block = extract_comment_block(inner_soup, "10 IssuedDT-Data").get_text(strip=True)
                        issued_date, issued_time = issued_block.split("-")
                        # Store original string data
                        earthquake_info["issued_date_str"] = issued_date.strip()
                        earthquake_info["issued_time_str"] = issued_time.strip()
                        # Convert to datetime object
                        earthquake_info["issued_datetime"] = parse_datetime(issued_date.strip(), issued_time.strip())
                        logger.debug(f"Extracted issued datetime: {earthquake_info['issued_datetime']}")
                    except (AttributeError, ValueError) as e:
                        logger.error(f"Error extracting issued date/time: {e}")
                        earthquake_info["issued_date_str"] = ""
                        earthquake_info["issued_time_str"] = ""
                        earthquake_info["issued_datetime"] = None

                    # Extract Authors
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

                    # Add the earthquake info to the list
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


# Step 1: Find the comment node
def get_comment_node(soup, target_comment):
    """Find a specific comment node in the soup"""
    logger.debug(f"Searching for comment node: '{target_comment}'")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if target_comment in comment:
            logger.debug(f"Found comment node: '{target_comment}'")
            return comment
    logger.warning(f"Comment node '{target_comment}' not found")
    return None


# Step 2: Get all <a> tags after the comment
def get_all_links_after_comment(soup, comment_text):
    """Get all links after a specific comment"""
    logger.debug(f"Getting links after comment: '{comment_text}'")
    comment_node = get_comment_node(soup, comment_text)
    if not comment_node:
        logger.warning(f"Comment node '{comment_text}' not found, cannot extract links")
        return []

    links = []
    current = comment_node

    while True:
        current = current.next_element
        if current is None:
            break
        if isinstance(current, Tag) and current.name == "a":
            links.append(current)

    logger.debug(f"Found {len(links)} links after comment '{comment_text}'")
    return links


# Helper function to serialize datetime objects for JSON
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


# Main execution
try:
    logger.info("Starting extraction of current month earthquake data")
    current_month_data = extract_monthly_earthquake_data(soup, BASE_URL)
    logger.info(f"Extracted {len(current_month_data)} earthquake events from current month")
    
    logger.info("Finding links to historical months")
    links = get_all_links_after_comment(soup, "end of last event")
    
    months_url = []
    for link in links:
        href = link.get("href")
        months_url.append(href)
    
    logger.info(f"Found {len(months_url)} historical month links")
    logger.debug(f"Month URLs: {months_url}")
    
    historical_data = []
    for i, month_url in enumerate(months_url, 1):
        logger.info(f"Processing historical month {i}/{len(months_url)}: {month_url}")
        try:
            response = requests.get(month_url, verify=False)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            logger.debug(f"Successfully fetched month page (Status: {response.status_code})")
            
            monthly_events = extract_monthly_earthquake_data(soup, month_url)
            historical_data.extend(monthly_events)
            logger.info(f"Added {len(monthly_events)} events from {month_url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch month page {month_url}: {e}")
            continue
    
    logger.info(f"Extracted {len(historical_data)} total historical earthquake events")
    
    # all_data = current_month_data + historical_data
    all_data = current_month_data
    logger.info(f"Combined data contains {len(all_data)} total earthquake events")
    
    try:
        output_file = "earthquake_data_v1.json"
        import json
        with open(output_file, "w") as json_file:
            json.dump(all_data, json_file, default=json_serial, indent=4, ensure_ascii=False)
        logger.info(f"Successfully saved data to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save data to file: {e}")

except Exception as e:
    logger.exception(f"Script execution failed with error: {e}")
    raise

logger.info("Script execution completed")