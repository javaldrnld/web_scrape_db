"""
ASSUMING THAT THE HTML STRUCTURE IS STILL LIKE THAT SINCE THIS CODE IS NOT ADAPTIVE
"""


import re

import polars as pl
import requests
from bs4 import BeautifulSoup

URL = "https://earthquake.phivolcs.dost.gov.ph/2025_Earthquake_Information/April/2025_0425_2047_B3F.html"
# URL = "https://earthquake.phivolcs.dost.gov.ph/2025_Earthquake_Information/April/2025_0423_1106_B1.html"
response = requests.get(URL, verify=False)

soup = BeautifulSoup(response.content, "lxml")

# Finding the Earthquake information
# Since find_all return list, we can use index
# And by using inspect element we can identify that all information are in the table
# tr[0] -> Earthquake information info
eq_info = soup.find_all("tr")[0]

# Additionally, if we look further more there's td and p, but we can see that there's span
# by identifying it is inside of the bold and another span, so it is in index 2
span_eq = eq_info.find_all("span")[2]
# to get that text, we use either .text or get_text, then we split them and get the last index
eq_no = span_eq.get_text().split()[-1]
#print("EQ NUMBER: ", eq_no)

# Getting the date time 
# Constant since 2nd table row siya? I mean yeh
SECOND_TR = soup.find_all("tr")[1]

# Get datetime from second TR, as stackoverflow said, we don't need to find tbody
# reference: https://stackoverflow.com/a/20523151
datetime_tr = SECOND_TR.find_all("tr")[0]
datetime_p = datetime_tr.find_all("p")[1]
date, time = datetime_p.get_text(strip=True).split("-")
# print(date, time)

# Get the location so refer parin sa second tr
location_tr = SECOND_TR.find_all("tr")[1]
location_p = location_tr.find_all("p")[1]
info = location_p.get_text()
lat, lon = re.findall(r"\d+\.\d+°[A-Z]", info)
region = re.findall(r"(\d{3}\s+.*)", info)[0].strip()
# print(lat, lon, region)

# Get the Depth of Focus (KM) in the third table
depth_foc_tr = SECOND_TR.find_all("tr")[2]
depth_foc_p = depth_foc_tr.find_all("p")[1]
depth_foc_info = depth_foc_p.get_text().strip()
# print(depth_foc_info)

# Get the Origin
origin_tr = SECOND_TR.find_all("tr")[3]
origin_p = origin_tr.find_all("p")[1]
origin_info = origin_p.get_text().strip()
# print(origin_info)

# Get the Magnitude
mag_tr = SECOND_TR.find_all("tr")[4]
mag_p = mag_tr.find_all("p")[1]
mag_info = mag_p.get_text().strip()
# print(mag_info)

### REPORTED INTENSITIES
THIRD_TR = soup.find_all("div")
reported_p = THIRD_TR[1].find_all("p")[5]
reported_txt = reported_p.get_text(strip=True)
if reported_txt == "":
    print("Here")
else:
    print(reported_txt)
#for i, val in enumerate(reported_p):
    #print(f"Index {i}: {val}")