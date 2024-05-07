import io
import random
from flask import Flask, send_file, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from passlib.hash import pbkdf2_sha256
from matplotlib.figure import Figure
import csv

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

    @classmethod
    def get(cls, user_id):
        with open('data/users.csv', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 4:
                    id, username, hashed_password, role = row
                    if str(id) == str(user_id):
                        return cls(id, username, role)
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with open('data/users.csv', 'r') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) == 4:
                    user_id, user_name, hashed_password, role = row
                    if username == user_name and pbkdf2_sha256.verify(password, hashed_password):
                        user = User(user_id, username, role)
                        login_user(user)
                        return redirect(url_for('home'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    page = request.args.get('page')
    data_range = int(request.args.get('data_range', '10'))
    if page == 'page1':
        content = "Ceci est le contenu de la Page 1."
        image = url_for('plot_png', data_pattern=1, data_range=data_range)
    elif page == 'page2':
        image = url_for('plot_png', data_pattern=2, data_range=data_range)
    else:
        image = url_for('plot_png', data_pattern=0, data_range=data_range)
    return render_template('home.html', image=image)



def create_figure(data_pattern, data_range):
    fig = Figure(figsize=(8, 6))  # Taille en pouces (800x600 pixels à 100 dpi)
    axis = fig.add_subplot(1, 1, 1)
    xs = range(data_range)
    if data_pattern == 1:
        ys = [random.randint(1, 50) for _ in xs]
    elif data_pattern == 2:
        ys = [random.randint(50, 100) for _ in xs]
    else:
        ys = [random.randint(1, 100) for _ in xs]
    axis.plot(xs, ys)
    return fig

@app.route('/plot/<int:data_pattern>/<int:data_range>.png')
@login_required
def plot_png(data_pattern, data_range):
    fig = create_figure(data_pattern, data_range)
    output = io.BytesIO()
    fig.savefig(output, format='png')
    output.seek(0)
    return send_file(output, mimetype='image/png')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = 'user'
        hashed_password = pbkdf2_sha256.hash(password)
        with open('data/users.csv', 'r') as csvfile:
            reader = csv.reader(csvfile)
            existing_ids = [int(row[0]) for row in reader if row and len(row) > 0]
            user_id = max(existing_ids) + 1 if existing_ids else 1
        with open('data/users.csv', 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([user_id, username, hashed_password, role])
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True)
