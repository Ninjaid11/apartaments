from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = '123'

ADMIN_PASSWORD = "123"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

DATABASE = 'app.db'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# подключение к бд
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# обработчик ошибок
@app.errorhandler(ValueError)
def handle_invalid_file_format(error):
    flash(str(error), 'danger')
    return redirect(request.url)

# получить id
def get_apartment_by_id(apartment_id):
    conn = get_db()
    apartment = conn.execute('SELECT * FROM apartments WHERE id = ?', (apartment_id,)).fetchone()
    conn.close()
    return apartment

# допустимое расширение
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(photo):
    if not allowed_file(photo.filename):
        flash("Недопустимый формат файла", "danger")
        raise ValueError("Недопустимый формат файла")
    filename = secure_filename(photo.filename)
    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    photo.save(photo_path)
    return filename


# обновление записи
def update_apartment(apartment_id, title, description, price, city, district, rooms, floor, photo_filename,
                     additional_photo_filename, apartments_class):
    conn = get_db()
    cursor = conn.cursor()
    query = """UPDATE apartments SET title = ?, description = ?, price = ?, city = ?, district = ?, rooms = ?, floor = ?, photo = ?, additional_photo = ?, apartments_class = ? WHERE id = ?"""
    values = (title, description, price, city, district, rooms, floor, photo_filename, additional_photo_filename,
              apartments_class, apartment_id)
    cursor.execute(query, values)
    conn.commit()
    conn.close()


# коментарии
def add_comment(apartment_id, author, content):
    conn = get_db()
    cursor = conn.cursor()
    query = "INSERT INTO comments (apartment_id, author, content) VALUES (?, ?, ?)"
    cursor.execute(query, (apartment_id, author, content))
    conn.commit()
    conn.close()


def get_comments(apartment_id):
    conn = get_db()
    query = "SELECT * FROM comments WHERE apartment_id = ? ORDER BY created_at DESC"
    comments = conn.execute(query, (apartment_id,)).fetchall()
    conn.close()
    return comments



# таблица
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS apartments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        price REAL NOT NULL,
        city TEXT NOT NULL,
        district TEXT,
        rooms INTEGER,
        floor INTEGER,
        apartments_class TEXT,
        photo TEXT,
        additional_photo TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apartment_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (apartment_id) REFERENCES apartments (id)
        )''')

    conn.commit()
    conn.close()


@app.route('/', methods=['GET'])
def home():
    min_price = request.args.get('min_price', type=float, default=0)
    max_price = request.args.get('max_price', type=float, default=float('inf'))
    city = request.args.get('city', default="").strip()
    district = request.args.get('district', default="").strip()
    rooms = request.args.get('rooms', type=int)
    floor = request.args.get('floor', type=int)
    apartments_class = request.args.get('apartments_class', default="").strip()

    conn = get_db()

    query = '''
        SELECT * FROM apartments 
        WHERE price >= ? AND price <= ? 
        AND LOWER(city) LIKE LOWER(?) 
        AND LOWER(district) LIKE LOWER(?)
    '''
    params = [min_price, max_price, f"%{city}%", f"%{district}%"]

    if rooms is not None:  # Если указано
        query += ' AND rooms = ?'
        params.append(rooms)

    if floor is not None:
        query += ' AND floor = ?'
        params.append(floor)

    if apartments_class:
        query += ' AND apartments_class = ?'
        params.append(apartments_class)

    apartments = conn.execute(query, params).fetchall()

    conn.close()

    return render_template('home.html', apartments=apartments)


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Неверный пароль. Доступ запрещён.', 'danger')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')


@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    conn = get_db()

    # параметры поиска из URL
    search_title = request.args.get('search_title', '')
    search_city = request.args.get('search_city', '')
    search_district = request.args.get('search_district', '')
    search_apartments_class = request.args.get('search_apartments_class', '')

    # строим запрос с фильтрацией, если есть параметры поиска
    query = 'SELECT * FROM apartments WHERE 1=1'
    params = []

    if search_title:
        query += ' AND title LIKE ?'
        params.append(f'%{search_title}%')

    if search_city:
        query += ' AND city LIKE ?'
        params.append(f'%{search_city}%')

    if search_district:
        query += ' AND district LIKE ?'
        params.append(f'%{search_district}%')

    if search_apartments_class:
        query += ' AND apartments_class LIKE ?'
        params.append(f'%{search_apartments_class}%')

    apartments = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('admin_dashboard.html', apartments=apartments, search_title=search_title,
                           search_city=search_city, search_district=search_district,
                           search_apartments_class=search_apartments_class)


@app.route('/admin/add_apartment', methods=['GET', 'POST'])
def add_apartment():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        city = request.form['city']
        district = request.form['district']
        rooms = request.form['rooms']
        floor = request.form['floor']
        apartments_class = request.form['apartments_class']

        # работа с загруженными фотографиями
        main_photo_filename = None
        additional_photo_filename = None

        if 'photo' in request.files:
            photo = request.files['photo']
            if photo.filename != '':
                main_photo_filename = secure_filename(photo.filename)
                main_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], main_photo_filename)
                photo.save(main_photo_path)

        if 'additional_photo' in request.files:
            additional_photo = request.files['additional_photo']
            if additional_photo.filename != '':
                additional_photo_filename = secure_filename(additional_photo.filename)
                additional_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], additional_photo_filename)
                additional_photo.save(additional_photo_path)

        if not title or not price or not city or not apartments_class:
            flash('Пожалуйста, заполните все обязательные поля.', 'danger')
            return redirect(request.url)

        conn = get_db()
        conn.execute(
            '''
            INSERT INTO apartments (title, description, price, city, district, rooms, floor, apartments_class, photo, additional_photo) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (title, description, price, city, district, rooms, floor, apartments_class, main_photo_filename,
             additional_photo_filename)
        )
        conn.commit()
        flash('Квартира успешно добавлена!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('add_apartment.html', apartments_classes=["Economy", "Standard", "Luxury"])


@app.route('/admin/delete_apartment/<int:apartment_id>')
def delete_apartment(apartment_id):
    conn = get_db()
    conn.execute('DELETE FROM apartments WHERE id = ?', (apartment_id,))
    conn.commit()
    conn.close()
    flash('Квартира успешно удалена.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/apartment/<int:apartment_id>')
def apartment_details(apartment_id):
    conn = get_db()
    apartment = conn.execute('SELECT * FROM apartments WHERE id = ?', (apartment_id,)).fetchone()
    conn.close()
    apartments = get_apartment_by_id(apartment_id)
    comments = get_comments(apartment_id)

    if not apartment:
        flash('Квартира не найдена.', 'danger')
        return redirect(url_for('home'))

    return render_template('apartment_details.html', apartment=apartment, apartments=apartments, comments=comments)


@app.route('/add_comment/<int:apartment_id>', methods=['POST'])
def add_comment_route(apartment_id):
    author = request.form.get('author')
    content = request.form.get('content')
    if not author or not content:
        flash("Все поля обязательны для заполнения!", "danger")
        return redirect(request.referrer)

    add_comment(apartment_id, author, content)
    flash("Комментарий успешно добавлен!", "success")
    return redirect(f'/apartment/{apartment_id}')


@app.route('/buy/<int:apartment_id>', methods=['GET', 'POST'])
def buy_apartment(apartment_id):
    conn = get_db()
    apartment = conn.execute('SELECT * FROM apartments WHERE id = ?', (apartment_id,)).fetchone()
    conn.close()

    if not apartment:
        flash('Квартира не найдена.', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        flash(f'Спасибо за покупку!', 'success')
        return redirect(url_for('home'))

    return render_template('buy_apartment.html', apartment=apartment)


@app.route('/edit_apartment/<int:apartment_id>', methods=['GET', 'POST'])
def edit_apartment(apartment_id):
    apartment = get_apartment_by_id(apartment_id)

    if not apartment:
        return "Apartment not found", 404

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        city = request.form['city']
        district = request.form['district']
        rooms = request.form['rooms']
        floor = request.form['floor']
        apartments_class = request.form['apartments_class']

        # обработка файлов
        photo = request.files.get('photo')
        additional_photo = request.files.get('additional_photo')

        # сохраняем фото, если оно загружено
        if photo and allowed_file(photo.filename):
            photo_filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
        else:
            photo_filename = apartment['photo']

        if additional_photo and allowed_file(additional_photo.filename):
            additional_photo_filename = secure_filename(additional_photo.filename)
            additional_photo.save(os.path.join(app.config['UPLOAD_FOLDER'], additional_photo_filename))
        else:
            additional_photo_filename = apartment['additional_photo']

        if not title or not price or not city or not apartments_class:
            flash('Пожалуйста, заполните все обязательные поля.', 'danger')
            return redirect(request.url)

        # обновления данных
        update_apartment(apartment_id, title, description, price, city, district, rooms, floor, photo_filename,
                         additional_photo_filename, apartments_class)

        return redirect(url_for('admin_dashboard', apartment_id=apartment_id))

    return render_template('edit_apartment.html', apartment=apartment,
                           apartments_classes=["Economy", "Standard", "Luxury"])


if __name__ == '__main__':
    init_db()  # вызываем функцию инициализации базы данных
    app.run(debug=True)