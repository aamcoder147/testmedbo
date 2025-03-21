from flask import Flask, render_template, json, request, redirect, url_for, send_from_directory, flash,jsonify
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='static')

# Required for flash messages
app.secret_key = '1234'  # Replace with a real secret key

# Initialize database
def init_db():
    if not os.path.exists('database'):
        os.makedirs('database')
    
    conn = sqlite3.connect('database/bookings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doctor_id INTEGER,
                  doctor_name TEXT,
                  patient_name TEXT,
                  patient_phone TEXT,
                  booking_date TEXT,
                  booking_time TEXT,
                  notes TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Load doctors data
with open('doctors.json') as f:
    doctors_data = json.load(f)

@app.route('/')
def home():
    # Pass the doctors data to the index.html template
    return render_template('index.html', doctors=doctors_data['doctors'])

@app.route('/')
def t():
    # Pass the doctors data to the index.html template
    return render_template('t.html')

@app.route('/booking/<int:doctor_id>')
def booking_page(doctor_id):
    try:
        doctor = next(d for d in doctors_data['doctors'] if d['id'] == doctor_id)
        today = datetime.today().strftime('%Y-%m-%d')  # Get today's date
        return render_template('doctors/booking.html', 
                             doctor=doctor,
                             doctor_id=doctor_id,
                             today=today,
                             availability=doctor['availability'])  # Pass availability to the template
    except StopIteration:
        return redirect(url_for('home'))

@app.route('/doctors.json')
def get_doctors():
    return send_from_directory('.', 'doctors.json')

@app.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    # Get form data
    doctor_id = request.form['doctor_id']
    doctor_name = request.form['doctor_name']
    patient_name = request.form['patient_name']
    patient_phone = request.form['patient_phone']
    booking_date = request.form['booking_date']
    booking_time = request.form['booking_time']
    selected_day = datetime.strptime(booking_date, '%Y-%m-%d').strftime('%A')
    
    # Find the doctor
    doctor = next(d for d in doctors_data['doctors'] if d['id'] == int(doctor_id))
    
    # Validate booking rules
    conn = sqlite3.connect('database/bookings.db')
    c = conn.cursor()
    
    # Rule 1: Check if the booking date is in the past
    today = datetime.today().strftime('%Y-%m-%d')
    if booking_date < today:
        flash('⛔ You cannot book on a date before today.', 'error')
        return redirect(url_for('booking_page', doctor_id=doctor_id))
    
        # Check if the doctor is unavailable on the selected day
    if "Unavilable" in doctor['availability'].get(selected_day, []):
        flash('⛔ الطبيب غير متوفر في هذا اليوم.', 'error')
        return redirect(url_for('booking_page', doctor_id=doctor_id))
    
    # Rule 2: Check if the same name has booked the same doctor within 5 days
    c.execute('''SELECT * FROM bookings 
                 WHERE patient_name = ? AND doctor_id = ? 
                 AND DATE(booking_date) >= DATE(?, '-5 days')''',
              (patient_name, doctor_id, booking_date))
    if c.fetchone():
        flash('⛔ You can only book the same doctor once every 5 days.', 'error')
        return redirect(url_for('booking_page', doctor_id=doctor_id))
    
    # Rule 10: Check if the time slot is already booked
    c.execute('''SELECT * FROM bookings 
                 WHERE doctor_id = ? AND booking_date = ? AND booking_time = ?''',
              (doctor_id, booking_date, booking_time))
    if c.fetchone():
        flash('⛔ This time slot is already booked. Please choose another time.', 'error')
        return redirect(url_for('booking_page', doctor_id=doctor_id))
    
    # Rule 11: Check if the same name or phone has a booking on the same day
    c.execute('''SELECT * FROM bookings 
                 WHERE (patient_name = ? OR patient_phone = ?) AND booking_date = ?''',
              (patient_name, patient_phone, booking_date))
    if c.fetchone():
        flash('⛔ You already have a booking on this day. Only one booking per day is allowed.', 'error')
        return redirect(url_for('booking_page', doctor_id=doctor_id))
    
    # Save to database
    c.execute('''INSERT INTO bookings 
                 (doctor_id, doctor_name, patient_name, patient_phone, booking_date, booking_time)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (doctor_id, doctor_name, patient_name, patient_phone, booking_date, booking_time))
    conn.commit()
    
    # Get the last inserted booking ID
    booking_id = c.lastrowid
    conn.close()
    
    # Redirect to confirmation page with booking ID
    return redirect(url_for('confirmation', 
                          booking_id=booking_id,
                          doctor_name=doctor_name,
                          patient_name=patient_name,
                          booking_date=booking_date,
                          booking_time=booking_time))

@app.route('/confirmation')
def confirmation():
    booking_id = request.args.get('booking_id')
    if not booking_id:
        return redirect(url_for('home'))
    
    return render_template('confirmation.html',
                         booking_id=booking_id,
                         doctor_name=request.args.get('doctor_name'),
                         patient_name=request.args.get('patient_name'),
                         booking_date=request.args.get('booking_date'),
                         booking_time=request.args.get('booking_time'))

@app.route('/delete-booking/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id):
    # Delete the booking from the database
    conn = sqlite3.connect('database/bookings.db')
    c = conn.cursor()
    
    # Get booking details before deletion
    c.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,))
    booking = c.fetchone()
    
    if booking:
        # Delete the booking
        c.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
        conn.commit()
        flash('✅ Your booking has been successfully deleted.', 'success')
    else:
        flash('⛔ Booking not found. It may have already been deleted.', 'error')
    
    conn.close()
    
    # Redirect based on the source of the request
    source = request.form.get('source')
    if source == 'confirmation':
        return redirect(url_for('home'))  # Redirect to the home page
    elif source == 'dashboard':
        patient_identifier = request.form.get('patient_identifier')
        return redirect(url_for('patient_dashboard', patient_identifier=patient_identifier))
    else:
        return redirect(url_for('home'))  # Default fallback

@app.route('/doctor-login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        doctor_name = request.form['doctorName']
        doctor_id = request.form['doctorId']
        
        # Check if the doctor exists
        doctor = next((d for d in doctors_data['doctors'] if d['name'] == doctor_name and str(d['id']) == doctor_id), None)
        
        if doctor:
            return redirect(url_for('doctor_dashboard', doctor_id=doctor_id))
        else:
            flash('⛔ Invalid doctor name or ID.', 'error')
            return redirect(url_for('doctor_login'))  # Redirect back to the login page
    
    return render_template('doctor_login.html')
@app.route('/doctor-dashboard/<int:doctor_id>')
def doctor_dashboard(doctor_id):
    # Fetch bookings for the doctor, ordered by date and time
    conn = sqlite3.connect('database/bookings.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM bookings 
                 WHERE doctor_id = ? 
                 ORDER BY booking_date ASC, booking_time ASC''', (doctor_id,))
    bookings = c.fetchall()
    conn.close()
    
    # Organize bookings by month and then by day
    bookings_by_month = {}
    for booking in bookings:
        booking_date = datetime.strptime(booking[5], '%Y-%m-%d')
        month_year = booking_date.strftime('%B %Y')  # e.g., "October 2023"
        day = booking_date.strftime('%Y-%m-%d')      # e.g., "2023-10-05"
        
        if month_year not in bookings_by_month:
            bookings_by_month[month_year] = {}
        
        if day not in bookings_by_month[month_year]:
            bookings_by_month[month_year][day] = []
        
        bookings_by_month[month_year][day].append(booking)
    
    return render_template('doctor_dashboard.html', 
                         bookings_by_month=bookings_by_month,
                         doctor_id=doctor_id)  # Pass doctor_id to the template

@app.route('/update-notes/<int:booking_id>', methods=['POST'])
def update_notes(booking_id):
    notes = request.form['notes']
    doctor_id = request.form['doctor_id']  # Get doctor_id from the form
    
    # Update the booking with notes
    conn = sqlite3.connect('database/bookings.db')
    c = conn.cursor()
    c.execute('''UPDATE bookings 
                 SET notes = ? 
                 WHERE id = ?''', (notes, booking_id))
    conn.commit()
    conn.close()
    
    flash('✅ Notes updated successfully.', 'success')
    return redirect(url_for('doctor_dashboard', doctor_id=doctor_id))  # Pass doctor_id as a URL # Pass doctor_id as a URL parameter

@app.route('/update-all-notes', methods=['POST'])
def update_all_notes():
    data = request.get_json()
    updates = data.get('updates', [])

    try:
        conn = sqlite3.connect('database/bookings.db')
        c = conn.cursor()

        for update in updates:
            booking_id = update.get('bookingId')
            notes = update.get('notes')
            c.execute('''UPDATE bookings 
                         SET notes = ? 
                         WHERE id = ?''', (notes, booking_id))

        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error updating notes: {e}")
        return jsonify({'success': False})
    
@app.route('/patient-login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        patient_identifier = request.form['patientIdentifier']
        
        # Check if the patient has any bookings
        conn = sqlite3.connect('database/bookings.db')
        c = conn.cursor()
        c.execute('''SELECT * FROM bookings 
                     WHERE patient_name = ? OR patient_phone = ? 
                     ORDER BY booking_date, booking_time''', 
                  (patient_identifier, patient_identifier))
        bookings = c.fetchall()
        conn.close()
        
        if bookings:
            return redirect(url_for('patient_dashboard', patient_identifier=patient_identifier))
        else:
            flash('⛔ No bookings found for this name or phone number.', 'error')
            return redirect(url_for('patient_login'))
    
    return render_template('patient_login.html')

@app.route('/patient-dashboard/<patient_identifier>')
def patient_dashboard(patient_identifier):
    # Fetch bookings for the patient
    conn = sqlite3.connect('database/bookings.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM bookings 
                 WHERE patient_name = ? OR patient_phone = ? 
                 ORDER BY booking_date, booking_time''', 
              (patient_identifier, patient_identifier))
    bookings = c.fetchall()
    conn.close()

    # Get current datetime for comparison
    current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M')

    return render_template('patient_dashboard.html', 
                         bookings=bookings, 
                         current_datetime=current_datetime,
                         patient_identifier=patient_identifier)
if __name__ == '__main__':
    app.run(debug=True, port=5000)