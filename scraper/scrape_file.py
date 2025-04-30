import re

import polars as pl
import requests
from bs4 import BeautifulSoup, Comment

EQ_INFO_LIST = []
URL = "https://earthquake.phivolcs.dost.gov.ph/2025_Earthquake_Information/April/2025_0427_1718_B2F.html"

response = requests.get(URL, verify=False)

soup = BeautifulSoup(response.content, "html.parser")

def extract_comment_block(soup, comment_text):
    # Find the specific comment
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if comment_text in comment:
            # Get the parent element containing this comment
            parent = comment.parent
            
            # Return parent only since its only needed and strip the text
            return parent


eq_block = extract_comment_block(soup, "1 EQInfo-Data").get_text(strip=True)
eq_no = eq_block
print(eq_no)

datetime_block = extract_comment_block(soup, "2 DateTime-Data").get_text(strip=True)
date, time = datetime_block.split("-")
print(date, time)

location_block = extract_comment_block(soup, "3 Location-Data").get_text(strip=True)
lat, lon = re.findall(r"\d+\.\d+°[A-Z]", location_block)
region = re.findall(r"(\d{3}\s+.*)", location_block)[0].strip()
print(lat, lon)
print(region)

depth= extract_comment_block(soup, "4 Depth-Data").get_text(strip=True)
print(depth)

origin = extract_comment_block(soup, "5 Origin-Data").get_text(strip=True)
print(origin)

magnitude = extract_comment_block(soup, "6 Magnitude-Data").get_text(strip=True)
print(magnitude)

filename = extract_comment_block(soup, "8 Map-Data")
img_tag = filename.find("img")
src = img_tag.get("src").strip()[:-4]
print(src)

reported_block = extract_comment_block(soup, "7 Intensity-Data")

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

# Display results
print("Reported Intensities:")
for r in reported_intensities:
    print(r)

print("\nInstrumental Intensities:")
for i in instrumental_intensities:
    print(i)

issued_block = extract_comment_block(soup, "10 IssuedDT-Data").get_text(strip=True)
issued_date, issued_time = issued_block.split("-")
print(issued_date, issued_time)

prepared_block = extract_comment_block(soup, "11 PreparedBy-Data").get_text(strip=True)
authors = prepared_block.split("/")
print(authors)
authors_dict = {}
for i, author in enumerate(authors, start=1):
    authors_dict[f"auth_{i}"] = author.strip()

for num, auth in authors_dict.items():
    print(num, auth)


earthquake_info = {
    "eq_no": eq_no,
    "filename": src,
    "date": date.strip(),
    "time": time.strip(),
    "latitude": lat.strip(),
    "longitude": lon.strip(),
    "depth_km": depth.strip(),
    "magnitude": magnitude.strip(),
    "region": region.strip(),
    "reported_intensities": reported_intensities,
    "instrumental_intensities": instrumental_intensities,
    "authors": authors_dict  # Add the authors here
}
# Add the earthquake info to the list
EQ_INFO_LIST.append(earthquake_info)

# import json
# print(json.dumps(EQ_INFO_LIST, indent=4, ensure_ascii=False))
import pprint
pprint.pprint(EQ_INFO_LIST)