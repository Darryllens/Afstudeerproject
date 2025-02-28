from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Databaseverbinding
mydb = mysql.connector.connect(
    host='localhost',  # Pas aan naar je eigen database host
    user='Darryll',  # Jouw databasegebruiker
    password='Darryllens12',  # Jouw databasewachtwoord
    database='Drankjes'
)
mycursor = mydb.cursor(dictionary=True)

# Routes voor HTML-pagina's
@app.route('/')
def login():
    return render_template('user.html')

@app.route('/welcome.html')
def welcome():
    return render_template('welcome.html')

@app.route('/index.html')
def index():
    return render_template('index.html')

@app.route('/summary.html')
def summary():
    return render_template('summary.html')

# API-endpoints
@app.route('/add_drink.php', methods=['GET', 'POST', 'DELETE'])
def handle_drinks():
    if request.method == 'GET':
        try:
            mycursor.execute("SELECT * FROM drankjes")
            results = mycursor.fetchall()
            return jsonify({
                'success': True,
                'data': [{
                    'id': row['id'],
                    'naam': row['naam'],
                    'prijs': row['prijs'],
                    'toegevoegd_op': row['toegevoegd_op'].strftime('%Y-%m-%d %H:%M:%S')
                } for row in results]
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    elif request.method == 'POST':
        try:
            data = request.json
            if not data or 'drink' not in data or 'price' not in data:
                return jsonify({'success': False, 'error': 'Geen drankje of prijs opgegeven.'})

            sql = "INSERT INTO drankjes (naam, prijs, toegevoegd_op) VALUES (%s, %s, %s)"
            values = (data['drink'], float(data['price']), datetime.utcnow())
            mycursor.execute(sql, values)
            mydb.commit()

            return jsonify({
                'success': True,
                'message': f"{data['drink']} is toegevoegd aan de database voor €{data['price']}!"
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    elif request.method == 'DELETE':
        try:
            sql = "DELETE FROM drankjes"
            mycursor.execute(sql)
            mydb.commit()
            return jsonify({'success': True, 'message': 'Alle drankjes zijn verwijderd.'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    app.run(debug=True)
