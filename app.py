import random
import math
from io import BytesIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from weasyprint import HTML

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Change this to a secure secret key

# Configure SQLite database for API usage counts
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///api_usage.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Model to persist API usage
class APIUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), unique=True, nullable=False)
    count = db.Column(db.Integer, default=0)

# Initialize database and ensure provider records exist
with app.app_context():
    db.create_all()
    for provider in ['mapbox', 'openstreetmap', 'herewego']:
        if not APIUsage.query.filter_by(provider=provider).first():
            new_usage = APIUsage(provider=provider, count=0)
            db.session.add(new_usage)
    db.session.commit()

API_USAGE_LIMIT = 100  # Set your free API usage limit

def select_api_provider():
    """Randomly select a provider that hasn't exceeded its usage limit."""
    available = APIUsage.query.filter(APIUsage.count < API_USAGE_LIMIT).all()
    if not available:
        return None
    selected = random.choice(available)
    selected.count += 1
    db.session.commit()
    return selected.provider

def get_coordinates(postal_code):
    """
    Dummy function to convert a postal code into coordinates.
    Replace with a real geocoding API call to obtain actual latitude and longitude.
    """
    try:
        seed = int(postal_code)
    except ValueError:
        seed = 0
    random.seed(seed)
    lat = 1.3000 + random.random() * 0.1   # Near Singapore's latitude
    lng = 103.8000 + random.random() * 0.1   # Near Singapore's longitude
    return lat, lng

# ------------------- Nearest Neighbor TSP Functions -------------------
def compute_euclidean_distance(coord1, coord2):
    """Calculate Euclidean distance between two (lat, lng) points."""
    return math.hypot(coord1[0] - coord2[0], coord1[1] - coord2[1])

def create_distance_matrix(coordinates):
    """
    Build a distance matrix for the list of coordinates.
    coordinates: List of tuples [(lat, lng), ...]
    Returns: 2D list representing the distance between each pair.
    """
    size = len(coordinates)
    distance_matrix = []
    for i in range(size):
        row = []
        for j in range(size):
            distance = compute_euclidean_distance(coordinates[i], coordinates[j])
            row.append(distance)
        distance_matrix.append(row)
    return distance_matrix

def nearest_neighbor_tsp(distance_matrix, start_index=0):
    """
    A simple nearest neighbor TSP solver.
    Returns the order of indices for the route.
    """
    n = len(distance_matrix)
    unvisited = list(range(n))
    route = []
    current = start_index
    route.append(current)
    unvisited.remove(current)
    
    while unvisited:
        next_node = min(unvisited, key=lambda x: distance_matrix[current][x])
        route.append(next_node)
        unvisited.remove(next_node)
        current = next_node
    return route

def real_route_optimizer(postal_codes, start=None, end=None):
    """
    Use a simple nearest neighbor algorithm to determine the route order.
    - Converts postal codes to coordinates.
    - Builds a distance matrix.
    - Uses the nearest neighbor algorithm to solve the TSP.
    - Adjusts for a fixed start and/or end if provided.
    """
    coords = [get_coordinates(code) for code in postal_codes]

    # Determine start index
    if start and start in postal_codes:
        start_index = postal_codes.index(start)
    else:
        start_index = 0

    distance_matrix = create_distance_matrix(coords)
    route_order = nearest_neighbor_tsp(distance_matrix, start_index=start_index)
    optimized_route = [postal_codes[i] for i in route_order]

    if end and end in postal_codes:
        if optimized_route[-1] != end:
            optimized_route = [code for code in optimized_route if code != end]
            optimized_route.append(end)
    return optimized_route

# ------------------- Flask Routes -------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Retrieve form data
        start_point = request.form.get("start_point")
        end_point = request.form.get("end_point")
        postal_codes_raw = request.form.get("postal_codes")
        # Captcha integration is on hold
        
        # Process comma-separated postal codes
        postal_codes = [code.strip() for code in postal_codes_raw.split(",") if code.strip()]
        if len(postal_codes) < 2 or len(postal_codes) > 15:
            flash("Enter at least 2 and at most 15 postal codes.")
            return redirect(url_for("index"))
        
        provider = select_api_provider()
        if not provider:
            flash("Free API usage limit exceeded. Please try again later.")
            return redirect(url_for("index"))
        
        optimized_route = real_route_optimizer(postal_codes, start=start_point, end=end_point)
        
        # Convert postal codes to coordinates for mapping
        route_coords = []
        for code in optimized_route:
            lat, lng = get_coordinates(code)
            route_coords.append({'postal_code': code, 'lat': lat, 'lng': lng})
        
        return render_template("results.html", 
                               optimized_route=optimized_route, 
                               route_coords=route_coords,
                               provider=provider,
                               start_point=start_point,
                               end_point=end_point)
    return render_template("index.html")

@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    # Get the optimized route from the hidden form field as a comma-separated string
    route_str = request.form.get("optimized_route", "")
    if route_str:
        optimized_route = route_str.split(',')
    else:
        optimized_route = []
    # Render the PDF template with the optimized route data
    rendered = render_template("pdf_template.html", optimized_route=optimized_route)
    pdf = HTML(string=rendered).write_pdf()
    # Create a filename with the current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"route_{timestamp}.pdf"
    return send_file(BytesIO(pdf), download_name=filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
