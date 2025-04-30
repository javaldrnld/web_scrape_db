
from bs4 import BeautifulSoup, Comment, Tag
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Get the HTML content
base_url = "https://earthquake.phivolcs.dost.gov.ph/"
response = requests.get(base_url, verify=False)
soup = BeautifulSoup(response.content, "html.parser")

# Step 1: Find the comment node
def get_comment_node(soup, target_comment):
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if target_comment in comment:
            return comment
    return None



# Step 2: Get all <a> tags after the comment
def get_all_links_after_comment(soup, comment_text):
    comment_node = get_comment_node(soup, comment_text)
    if not comment_node:
        return []

    links = []
    current = comment_node

    while True:
        current = current.next_element
        if current is None:
            break
        if isinstance(current, Tag) and current.name == "a":
            links.append(current)

    return links

# Usage
links = get_all_links_after_comment(soup, "end of last event")

print(links)
# Print the links (URLs and text)
for link in links:
    href = link.get("href")
    print(href)

# last_event_comment = get_comment_node(soup, "end of last event").get_text(strip=True)
# print(last_event_comment.next_element)

