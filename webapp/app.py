from flask import Flask, render_template, jsonify
import pymongo
from bson import json_util
import json
import os
import time

app = Flask(__name__)

# MongoDB connection with retry logic for Docker environment
def get_db():
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Using the Docker service name "mongodb" instead of localhost
            client = pymongo.MongoClient("mongodb://mongodb:27017/")
            db = client["earthquake_db"]
            collection = db["earthquake_data"]
            # Test the connection
            client.admin.command('ping')
            return collection
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"MongoDB connection attempt {attempt+1} failed. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                raise e

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/earthquakes')
def get_earthquakes():
    collection = get_db()
    documents = list(collection.find())
    # Handle MongoDB ObjectId serialization
    return json_util.dumps(documents)

@app.route('/api/earthquakes/<eq_no>')
def get_earthquake(eq_no):
    collection = get_db()
    document = collection.find_one({"eq_no": eq_no})
    # Handle MongoDB ObjectId serialization
    return json_util.dumps(document)

# Create templates folder and HTML files
os.makedirs('templates', exist_ok=True)

with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PHIVOLCS Earthquake Data Viewer</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .intensity-I { background-color: #ccffcc; }
        .intensity-II { background-color: #99ff99; }
        .intensity-III { background-color: #66ff66; }
        .intensity-IV { background-color: #ffff99; }
        .intensity-V { background-color: #ffcc99; }
        .card { margin-bottom: 20px; }
        .navbar { margin-bottom: 20px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="#">PHIVOLCS Earthquake Monitor</a>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row mb-4">
            <div class="col">
                <div class="alert alert-info">
                    Displaying earthquake data from PHIVOLCS. Data is collected and processed in real-time.
                </div>
            </div>
        </div>
        <div id="earthquakes-container"></div>
    </div>

    <template id="earthquake-template">
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">Earthquake #<span class="eq-no"></span></h2>
                <h6 class="card-subtitle mb-2 text-muted"><span class="date"></span> - <span class="time"></span></h6>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Location:</strong> <span class="region"></span></p>
                        <p><strong>Coordinates:</strong> <span class="latitude"></span>, <span class="longitude"></span></p>
                        <p><strong>Depth:</strong> <span class="depth"></span> km</p>
                        <p><strong>Magnitude:</strong> <span class="magnitude"></span></p>
                    </div>
                    <div class="col-md-6">
                        <div class="reported-intensities">
                            <h5>Reported Intensities</h5>
                            <ul class="reported-list"></ul>
                        </div>
                        <div class="instrumental-intensities">
                            <h5>Instrumental Intensities</h5>
                            <ul class="instrumental-list"></ul>
                        </div>
                    </div>
                </div>
                <div class="mt-3">
                    <small class="text-muted">Authors: <span class="authors"></span></small>
                </div>
            </div>
        </div>
    </template>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            fetch('/api/earthquakes')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('earthquakes-container');
                    const template = document.getElementById('earthquake-template');
                    
                    if (data.length === 0) {
                        const alert = document.createElement('div');
                        alert.className = 'alert alert-warning';
                        alert.textContent = 'No earthquake data found in the database.';
                        container.appendChild(alert);
                        return;
                    }
                    
                    data.forEach(earthquake => {
                        const card = template.content.cloneNode(true);
                        
                        // Fill in basic information
                        card.querySelector('.eq-no').textContent = earthquake.eq_no;
                        card.querySelector('.date').textContent = earthquake.date;
                        card.querySelector('.time').textContent = earthquake.time;
                        card.querySelector('.region').textContent = earthquake.region;
                        card.querySelector('.latitude').textContent = earthquake.latitude;
                        card.querySelector('.longitude').textContent = earthquake.longitude;
                        card.querySelector('.depth').textContent = earthquake.depth_km;
                        card.querySelector('.magnitude').textContent = earthquake.magnitude;
                        
                        // Fill in reported intensities
                        const reportedList = card.querySelector('.reported-list');
                        if (earthquake.reported_intensities && earthquake.reported_intensities.length > 0) {
                            earthquake.reported_intensities.forEach(intensity => {
                                const li = document.createElement('li');
                                li.className = `intensity-${intensity.intensity}`;
                                li.textContent = `Intensity ${intensity.intensity}: ${intensity.locations}`;
                                reportedList.appendChild(li);
                            });
                        } else {
                            card.querySelector('.reported-intensities').style.display = 'none';
                        }
                        
                        // Fill in instrumental intensities
                        const instrumentalList = card.querySelector('.instrumental-list');
                        if (earthquake.instrumental_intensities && earthquake.instrumental_intensities.length > 0) {
                            earthquake.instrumental_intensities.forEach(intensity => {
                                const li = document.createElement('li');
                                li.className = `intensity-${intensity.intensity}`;
                                li.textContent = `Intensity ${intensity.intensity}: ${intensity.locations}`;
                                instrumentalList.appendChild(li);
                            });
                        } else {
                            card.querySelector('.instrumental-intensities').style.display = 'none';
                        }
                        
                        // Fill in authors
                        const authors = [];
                        if (earthquake.authors) {
                            for (const key in earthquake.authors) {
                                if (earthquake.authors[key]) {
                                    authors.push(earthquake.authors[key]);
                                }
                            }
                        }
                        card.querySelector('.authors').textContent = authors.join(', ');
                        
                        container.appendChild(card);
                    });
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                    const container = document.getElementById('earthquakes-container');
                    const alert = document.createElement('div');
                    alert.className = 'alert alert-danger';
                    alert.textContent = 'Error loading earthquake data. Please try again later.';
                    container.appendChild(alert);
                });
        });
    </script>
</body>
</html>
    ''')

if __name__ == '__main__':
    # Use port 8050 to match your Docker Compose configuration
    app.run(host='0.0.0.0', port=8050, debug=True)