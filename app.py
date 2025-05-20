from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
from mysql.connector import Error
import time
import json
import os
from decimal import Decimal
from functools import wraps  # Toegevoegd voor decorators
from dotenv import load_dotenv  # Toegevoegd voor .env ondersteuning

load_dotenv()  # Laad .env bestand

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

app = Flask(__name__)
# Verbeterde beveiliging: random secret key genereren of uit env variabele halen
app.secret_key = os.getenv('SECRET_KEY')
app.json_encoder = DecimalEncoder

# Decorators voor routebeveiliging
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_name' not in session:
            return redirect(url_for('welcome'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_type' not in session or session['user_type'] != 'admin':
            return redirect(url_for('welcome'))
        return f(*args, **kwargs)
    return decorated_function

# Globale variabelen voor de laatst gescande kaart en redirects
last_scanned_uid = None
last_scan_time = 0

# Database connection function with improved security
def get_db_connection():
    try:
        # Haal database credentials uit .env bestand
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        return connection
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None

# Initial database connection
mydb = get_db_connection()
mycursor = mydb.cursor(dictionary=True) if mydb else None

@app.route("/")
def home():
    return render_template("user.html")

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/index")
def index():
    # Redirect to user's personal page if user_name is in session
    if 'user_name' in session and 'card_uid' in session:
        # First verify that the user still exists in the database
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            query = "SELECT * FROM users WHERE card_uid = %s"
            cursor.execute(query, (session['card_uid'],))
            user = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user:
                return redirect(url_for('user_index', user_name=session['user_name']))
            else:
                # User has been removed from database, clear session
                session.clear()
    
    return render_template("index.html")

@app.route("/user/<user_name>")
@login_required
def user_index(user_name):
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return redirect(url_for('welcome'))
            
        cursor = connection.cursor(dictionary=True)
            
        # Get user information
        query = "SELECT * FROM users WHERE name = %s"
        cursor.execute(query, (user_name,))
        user = cursor.fetchone()
        
        if not user:
            # User no longer exists in database
            session.clear()
            return redirect(url_for('welcome'))
        
        # Check if the logged-in user has access to this page
        if session.get('user_name') != user_name and session.get('user_type') != 'admin':
            return redirect(url_for('welcome'))
            
        # Get user's drinks from Bestellingen table
        drinks_query = """
            SELECT b.ID as id, d.Naam as drink_name, d.prijs as drink_price, 
                   b.Timestamp as added_on 
            FROM Bestellingen b
            JOIN Dranken d ON b.Drank_ID = d.ID
            WHERE b.User_ID = %s
            ORDER BY b.Timestamp DESC
        """
        cursor.execute(drinks_query, (user['id'],))
        user_drinks = cursor.fetchall()
        
        # Calculate total spent
        total_spent = sum(float(drink['drink_price']) for drink in user_drinks) if user_drinks else 0
        
        cursor.close()
        connection.close()
        
        return render_template("index.html", 
                              user_name=user_name, 
                              card_uid=user['card_uid'],
                              user_drinks=user_drinks,
                              total_spent=total_spent)
    except Error as e:
        print(f"Database error: {e}")
        return redirect(url_for('welcome'))

@app.route("/summary")
@admin_required  # Deze route vereist nu admin-rechten
def summary():
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return redirect(url_for('welcome'))
            
        cursor = connection.cursor(dictionary=True)
            
        # Get all users
        query = "SELECT * FROM users WHERE type = 'user' ORDER BY name"
        cursor.execute(query)
        users = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return render_template("summary.html", 
                              users=users,
                              kassa_user=session.get('user_name', 'Admin'))
    except Error as e:
        print(f"Database error: {e}")
        return redirect(url_for('welcome'))

@app.route("/registration")
def registration():
    # Haal het laatste gescande UID op voor automatisch invullen in registratie
    return render_template("Registration.html", card_uid=last_scanned_uid)

@app.route("/receive_nfc", methods=["POST"])
def receive_nfc():
    global last_scanned_uid, last_scan_time
    
    # Log alle headers en request data voor debugging
    print("Request headers:", dict(request.headers))
    
    try:
        data = request.get_json()
        print(f"Received data: {data}")  # Log the entire data payload
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Invalid JSON data"})
    
    # Sla de UID op in de globale variabele
    if data and 'uid' in data:
        uid = data['uid']
        last_scanned_uid = uid
        last_scan_time = time.time()  # Sla de huidige tijd op
        print(f"Laatste UID ontvangen: {uid}")
        
        # Get the current route if available
        current_route = data.get('current_route', '')
        print(f"Current route: {current_route}")
        
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return jsonify({
                "status": "error",
                "message": "Kan geen verbinding maken met de database"
            })
            
        cursor = connection.cursor(dictionary=True)
        
        # Check for user in users table
        query = "SELECT * FROM users WHERE card_uid = %s"
        cursor.execute(query, (uid,))
        user = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        if user:
            print("User found:", user)
            # Save user info in session
            session['user_name'] = user['name']
            session['card_uid'] = user['card_uid']
            session['user_id'] = user['id']  # Also save user ID in session
            session['user_type'] = user['type']  # Save user type (user/admin)
            
            # If user is admin, redirect to summary page
            if user['type'] == 'admin':
                return jsonify({
                    "status": "success",
                    "message": "Admin gebruiker gevonden",
                    "user": user,
                    "redirect": "/summary"  # Redirect to summary page
                })
            else:
                # Regular user, redirect to user page
                return jsonify({
                    "status": "success",
                    "message": "Gebruiker gevonden",
                    "user": user,
                    "redirect": f"/user/{user['name']}"  # Redirect to user's personal page
                })
        else:
            print("User not found for card:", uid)
            # Clear session if it exists
            session.clear()
            
            return jsonify({
                "status": "not_found",
                "message": "Gebruiker niet gevonden voor deze kaart",
                "card_uid": uid,
                "redirect": "/registration"  # Redirect to registration page
            })
    else:
        print("No UID received in JSON data")
        return jsonify({"status": "error", "message": "Geen UID ontvangen"})

@app.route("/check_scan")
def check_scan():
    global last_scanned_uid, last_scan_time
    
    # Get the current route
    current_route = request.args.get('route', '')
    print(f"Check scan called from route: {current_route}")
    
    # Controleer of er een recente scan is (binnen de laatste 10 seconden)
    if last_scanned_uid and time.time() - last_scan_time < 10:
        print(f"Recent scan found: {last_scanned_uid}")
        
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return jsonify({
                "status": "error",
                "message": "Kan geen verbinding maken met de database"
            })
            
        cursor = connection.cursor(dictionary=True)
        
        # Check for user in users table
        query = "SELECT * FROM users WHERE card_uid = %s"
        cursor.execute(query, (last_scanned_uid,))
        user = cursor.fetchone()
        
        # Reset laatste scan tijd
        last_scan_time = 0
        
        cursor.close()
        connection.close()
        
        if user:
            # Save user info in session
            session['user_name'] = user['name']
            session['card_uid'] = user['card_uid']
            session['user_id'] = user['id']  # Also save user ID in session
            session['user_type'] = user['type']  # Save user type (user/admin)
            
            # If user is admin, redirect to summary page
            if user['type'] == 'admin':
                return jsonify({
                    "status": "success",
                    "message": "Admin gebruiker gevonden",
                    "user": user,
                    "redirect": "/summary"  # Redirect to summary page
                })
            else:
                # Regular user, redirect to user page
                return jsonify({
                    "status": "success",
                    "message": "Gebruiker gevonden",
                    "user": user,
                    "redirect": f"/user/{user['name']}"  # Redirect to user's personal page
                })
        else:
            # Clear session if it exists
            session.clear()
            
            return jsonify({
                "status": "not_found",
                "message": "Gebruiker niet gevonden voor deze kaart",
                "card_uid": last_scanned_uid,
                "redirect": "/registration"  # Redirect to registration page
            })
    else:
        return jsonify({
            "status": "no_scan",
            "message": "Geen recente scan gevonden"
        })

# Route om nieuwe gebruiker te registreren
@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.form
    
    try:
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return render_template("registration.html", 
                                error="Kan geen verbinding maken met de database", 
                                card_uid=data.get('card_uid', ''))
            
        cursor = connection.cursor(dictionary=True)
            
        # Controleer of alle vereiste velden aanwezig zijn
        if 'card_uid' in data and 'name' in data:
            card_uid = data['card_uid']
            name = data['name']
            
            # Controleer of de naam geldig is (alleen alfanumerieke tekens)
            if not name.replace(' ', '').isalnum():
                cursor.close()
                connection.close()
                return render_template("registration.html", 
                                    error="Naam mag alleen letters en cijfers bevatten", 
                                    card_uid=card_uid)
            
            # Voeg de nieuwe gebruiker toe aan de database, default type is 'user'
            query = "INSERT INTO users (card_uid, name, type) VALUES (%s, %s, 'user')"
            cursor.execute(query, (card_uid, name))
            connection.commit()
            
            # Redirect naar de gebruikerspagina
            return redirect(url_for('user_index', user_name=name))
        else:
            cursor.close()
            connection.close()
            return render_template("registration.html", 
                                error="Alle velden zijn verplicht", 
                                card_uid=data.get('card_uid', ''))
            
    except Error as e:
        print(f"Database error: {e}")
        return render_template("registration.html", 
                            error=f"Database fout: {str(e)}", 
                            card_uid=data.get('card_uid', ''))

@app.route("/clear_user_orders", methods=["POST"])
@admin_required
def clear_user_orders():
    data = request.get_json()
    if not data or 'user_id' not in data:
        return jsonify({"success": False, "error": "Ontbrekende gebruikers-ID"})
    user_id = data['user_id']
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
        cursor = connection.cursor(dictionary=True)
        query = "DELETE FROM Bestellingen WHERE User_ID = %s"
        cursor.execute(query, (user_id,))
        connection.commit()
        cursor.close()
        connection.close()
        return jsonify({"success": True, "message": "Alle bestellingen verwijderd"})
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

@app.route("/delete_order", methods=["POST"])
@admin_required
def delete_order():
    data = request.get_json()
    if not data or 'order_id' not in data:
        return jsonify({"success": False, "error": "Ontbrekende order ID"})
    order_id = data['order_id']
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
        cursor = connection.cursor(dictionary=True)
        query = "DELETE FROM Bestellingen WHERE ID = %s"
        cursor.execute(query, (order_id,))
        connection.commit()
        cursor.close()
        connection.close()
        return jsonify({"success": True, "message": "Bestelling verwijderd"})
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

@app.route("/get_user_orders")
@login_required
def get_user_orders():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "Geen gebruikers-ID opgegeven"})
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
        cursor = connection.cursor(dictionary=True)
        query = """
        SELECT b.ID, b.Timestamp, d.Naam as drink_name, d.prijs as drink_price, d.categorie
        FROM Bestellingen b
        JOIN Dranken d ON b.Drank_ID = d.ID
        WHERE b.User_ID = %s
        ORDER BY b.Timestamp DESC
        """
        cursor.execute(query, (user_id,))
        orders = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify({"success": True, "orders": orders})
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

@app.route("/add_user_drink", methods=["POST"])
def add_user_drink():
    try:
        data = request.get_json()
        if not data or not all(key in data for key in ['user_name', 'drink_name', 'drink_price']):
            return jsonify({
                "success": False, 
                "error": "Ontbrekende vereiste gegevens"
            })
            
        user_name = data['user_name']
        drink_name = data['drink_name']
        drink_price = data['drink_price']
        drink_id = data.get('drink_id')

        connection = get_db_connection()
        if not connection:
            return jsonify({
                "success": False, 
                "error": "Kan geen verbinding maken met de database"
            })
            
        cursor = connection.cursor(dictionary=True)
        
        # Haal user op
        query = "SELECT * FROM users WHERE name = %s"
        cursor.execute(query, (user_name,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            connection.close()
            return jsonify({
                "success": False, 
                "error": f"Geen gebruiker gevonden met naam: {user_name}"
            })

        # Zoek drink_id indien niet opgegeven
        if not drink_id:
            query = "SELECT ID FROM Dranken WHERE Naam = %s AND prijs = %s"
            cursor.execute(query, (drink_name, drink_price))
            drink_result = cursor.fetchone()
            
            if not drink_result:
                query = "SELECT ID FROM Dranken WHERE Naam = %s"
                cursor.execute(query, (drink_name,))
                drink_result = cursor.fetchone()
                
                if not drink_result:
                    cursor.close()
                    connection.close()
                    return jsonify({
                        "success": False, 
                        "error": f"Drankje niet gevonden in de database: {drink_name}"
                    })
            
            drink_id = drink_result['ID']

        # Voeg alleen toe aan Bestellingen tabel
        insert_query = "INSERT INTO Bestellingen (Drank_ID, User_ID) VALUES (%s, %s)"
        cursor.execute(insert_query, (drink_id, user['id']))
        connection.commit()

        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": f"{drink_name} toegevoegd aan {user_name}'s rekening"
        })
        
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({
            "success": False,
            "error": f"Database fout: {str(e)}"
        })
    except Exception as e:
        print(f"General error: {e}")
        return jsonify({
            "success": False,
            "error": f"Algemene fout: {str(e)}"
        })

# Voeg deze route toe om drankjes op te halen
@app.route("/get_drinks")
def get_drinks():
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Haal alle drankjes op uit de Dranken tabel, gesorteerd op categorie
        query = "SELECT * FROM Dranken ORDER BY categorie, Naam"
        cursor.execute(query)
        drinks = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "drinks": drinks
        })
    except Exception as e:
        print(f"Error fetching drinks: {e}")
        return jsonify({"success": False, "error": f"Fout bij ophalen drankjes: {str(e)}"})

# Sessie-bescherming: instellen sessie timeout
@app.before_request
def session_timeout():
    session.permanent = True
    app.permanent_session_lifetime = 3600  # 1 uur sessie timeout

# Route voor logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('welcome'))

# 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route("/get_user_drinks")
@login_required
def get_user_drinks():
    user_name = request.args.get('user_name')
    if not user_name:
        return jsonify({"success": False, "error": "Geen gebruikersnaam opgegeven"})
    
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Eerst de user ID ophalen
        user_query = "SELECT id FROM users WHERE name = %s"
        cursor.execute(user_query, (user_name,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"success": False, "error": "Gebruiker niet gevonden"})
        
        # Bestellingen ophalen met drankgegevens
        drinks_query = """
            SELECT b.ID as id, d.Naam as drink_name, d.prijs as drink_price, 
                   b.Timestamp as added_on 
            FROM Bestellingen b
            JOIN Dranken d ON b.Drank_ID = d.ID
            WHERE b.User_ID = %s
            ORDER BY b.Timestamp DESC
        """
        cursor.execute(drinks_query, (user['id'],))
        drinks = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "drinks": drinks
        })
        
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/delete_drink", methods=["POST"])
@login_required
def delete_drink():
    data = request.get_json()
    if not data or 'drink_id' not in data:
        return jsonify({"success": False, "error": "Geen drink_id opgegeven"})
    
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Verwijder de bestelling uit de Bestellingen tabel
        delete_query = "DELETE FROM Bestellingen WHERE ID = %s"
        cursor.execute(delete_query, (data['drink_id'],))
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": "Drankje verwijderd"
        })
        
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/clear_user_drinks", methods=["POST"])
@login_required
def clear_user_drinks():
    data = request.get_json()
    if not data or 'user_name' not in data:
        return jsonify({"success": False, "error": "Geen gebruikersnaam opgegeven"})
    
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Eerst de user ID ophalen
        user_query = "SELECT id FROM users WHERE name = %s"
        cursor.execute(user_query, (data['user_name'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"success": False, "error": "Gebruiker niet gevonden"})
        
        # Alle bestellingen van deze gebruiker verwijderen
        delete_query = "DELETE FROM Bestellingen WHERE User_ID = %s"
        cursor.execute(delete_query, (user['id'],))
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": "Alle drankjes verwijderd"
        })
        
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/delete_user", methods=["POST"])
@admin_required
def delete_user():
    data = request.get_json()
    if not data or 'user_name' not in data:
        return jsonify({"success": False, "error": "Geen gebruikersnaam opgegeven"})
    
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Eerst de user ID ophalen
        user_query = "SELECT id FROM users WHERE name = %s"
        cursor.execute(user_query, (data['user_name'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"success": False, "error": "Gebruiker niet gevonden"})
        
        # Verwijder eerst alle bestellingen van de gebruiker
        delete_orders_query = "DELETE FROM Bestellingen WHERE User_ID = %s"
        cursor.execute(delete_orders_query, (user['id'],))
        
        # Verwijder dan de gebruiker zelf
        delete_user_query = "DELETE FROM users WHERE id = %s"
        cursor.execute(delete_user_query, (user['id'],))
        
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": "Gebruiker en alle bestellingen verwijderd"
        })
        
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})
    
if __name__ == "__main__":
    # Configuratie uit .env
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    app.run(host=host, port=port, debug=debug)