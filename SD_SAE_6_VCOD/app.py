import csv
import plotly.express as px
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from passlib.hash import pbkdf2_sha256
import folium
import geopandas as gpd
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
DATA_FOLDER = 'data'
USER_DATA_FOLDER = 'data_user'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role, status):
        self.id = id
        self.username = username
        self.role = role
        self.status = status

    @classmethod
    def get(cls, user_id):
        with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 5:
                    id, username, hashed_password, role, status = row
                    if str(id) == str(user_id):
                        return cls(id, username, role, status)
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
        with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'r') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) == 5:
                    user_id, user_name, hashed_password, role, status = row
                    if username == user_name and pbkdf2_sha256.verify(password, hashed_password):
                        if status == 'approuve':
                            user = User(user_id, username, role, status)
                            login_user(user)
                            return redirect(url_for('home'))
                        else:
                            return redirect(url_for('waiting'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/waiting')
def waiting():
    return render_template('waiting.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def creer_carte():
    # Créer une carte Folium centrée sur la France
    carte = folium.Map(
        location=[47.219303670107, 1.8390806604309],  # Centré sur la France
        zoom_start=6,
        scrollWheelZoom=False,
        tiles='CartoDB positron'
    )
    return carte

def afficher_carte(geojson_file, df, carte):
    # Créer une carte Folium
    choropleth = folium.Choropleth(
        geo_data=geojson_file,
        data=df,
        columns=('code_departement', 'tauxpourmille'),
        key_on="feature.properties.code",
        line_opacity=0.5,
        highlight=True
    )

    choropleth.geojson.add_to(carte)

    df = df.set_index('code_departement')
    for feature in choropleth.geojson.data['features']:
        code_departement = feature['properties']['code']
        nom_departement = feature['properties']['nom']

        if code_departement in df.index:
            pop_value = df.loc[code_departement, 'POP']
            taux_value = df.loc[code_departement, 'tauxpourmille']
            if isinstance(pop_value, pd.Series):
                pop_value = pop_value.iloc[0]
            if isinstance(taux_value, pd.Series):
                taux_value = taux_value.iloc[0]
            feature['properties']['nombre_population'] = 'Population : ' + str(pop_value)
            feature['properties']['taux_pour_mille'] = 'Taux pour mille : ' + f"{taux_value:.2f}"
        else:
            feature['properties']['nombre_population'] = 'Population : N/A'
            feature['properties']['taux_pour_mille'] = 'Taux pour mille : N/A'

    # afficher département quand la souris survole la carte
    choropleth.geojson.add_child(
        folium.features.GeoJsonTooltip(
            ['nom', 'code', 'nombre_population', 'taux_pour_mille'],
            labels=False
        )
    )

    return carte

@app.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    page = request.args.get('page')
    data_range = int(request.args.get('data_range', '10'))
    image = None
    images = []

    if page == 'page1':
        # Obtenir l'année et la classe de faits à partir des paramètres de la requête
        annee = request.args.get('annee_page1', default='Toutes', type=str)
        classe = request.args.get('classe', default='', type=str)

        # Filtrer les données en fonction de l'année et de la classe
        if annee != 'Toutes':
            filtered_data = departements_data[departements_data['annee'].astype(str) == annee]
        else:
            filtered_data = departements_data.copy()

        if classe:
            filtered_data = filtered_data[filtered_data['classe'] == classe]

        # Agréger les données pour obtenir la moyenne des taux pour mille par département
        aggregated_data = filtered_data.groupby('code_departement').agg(
            {'tauxpourmille': 'mean', 'POP': 'first'}).reset_index()

        # Fusionner les données GeoJSON dans les données agrégées
        departements_merged = aggregated_data.merge(departements_geo, left_on='code_departement', right_on='code',
                                                    how='left')

        # Filtrer les lignes avec des géométries valides
        departements_merged = departements_merged[departements_merged['geometry'].notnull()]

        # Créer la carte
        carte = creer_carte()
        carte = afficher_carte(geojson_file_path, departements_merged, carte)

        # Sauvegarder la carte dans un fichier HTML dans le répertoire static
        if not os.path.exists('static'):
            os.makedirs('static')
        carte.save('static/map.html')

        # Obtenir les années et les classes disponibles
        annees = ['Toutes'] + sorted(departements_data['annee'].astype(str).unique().tolist())
        classes = sorted(departements_data['classe'].unique().tolist())

        return render_template('home.html', page=page, annees=annees, classes=classes, selected_annee=annee, selected_classe=classe)

    elif page == 'page2':
        annee = request.form.get('annee_page2')
        departement = request.form.get('departement')

        # Filtrer les données selon les critères sélectionnés
        filtered_df = departements_data.copy()
        if annee:
            filtered_df = filtered_df[filtered_df['annee'].astype(str) == annee]
        if departement:
            filtered_df = filtered_df[filtered_df['nom_departement'] == departement]

        # Convertir la colonne 'faits' en numérique
        filtered_df['faits'] = pd.to_numeric(filtered_df['faits'], errors='coerce')

        # Graphique 1 : Top 5 des plus grandes classes par fait
        top5_classes = filtered_df.groupby('classe')['faits'].sum().nlargest(5).reset_index()
        fig1 = px.bar(top5_classes, x='classe', y='faits', title='Top 5 des plus grandes classes par fait')

        # Graphique 2 : Répartition des unités de compte
        fig2 = px.pie(filtered_df, names='unité.de.compte', values='faits', title='Répartition des unités de compte')

        # Graphique 3 : Évolution du nombre de faits
        evolution_faits = filtered_df.groupby('annee')['faits'].sum().reset_index()
        fig3 = px.line(evolution_faits, x='annee', y='faits', title='Évolution du nombre de faits')

        # Graphique 4 : Répartition des faits par classe
        fig4 = px.histogram(filtered_df, x='classe', y='faits', title='Répartition des faits par classe')

        graphs = [fig1, fig2, fig3, fig4]

        # Convertir les graphiques en HTML
        graph_divs = [fig.to_html(full_html=False) for fig in graphs]

        unique_annees = sorted(departements_data['annee'].astype(str).unique().tolist())
        unique_departements = sorted(departements_data['nom_departement'].unique().tolist())

        return render_template('home.html', page=page, graph_divs=graph_divs, unique_annees=unique_annees,
                               unique_departements=unique_departements, selected_annee=annee, selected_departement=departement)

    files = os.listdir(DATA_FOLDER)
    file_info = []
    for file in files:
        file_name, file_extension = os.path.splitext(file)
        file_info.append({'name': file_name, 'extension': file_extension, 'path': file})

    return render_template('home.html', page=page, data_range=data_range, image=image, images=images, files=file_info)


@app.route('/map')
@login_required
def map_view():
    return send_file('static/map.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = 'user'
        status = 'non_approuve'
        hashed_password = pbkdf2_sha256.hash(password)
        with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'r') as csvfile:
            reader = csv.reader(csvfile)
            existing_ids = [int(row[0]) for row in reader if row and len(row) > 0]
            user_id = max(existing_ids) + 1 if existing_ids else 1
        with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([user_id, username, hashed_password, role, status])
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        flash("Permission refusée, droit insuffisant", 'error')
        return redirect(url_for('home'))
    users = []
    with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 5:
                users.append({'id': row[0], 'username': row[1], 'role': row[3], 'status': row[4]})
    return render_template('admin.html', users=users)

@app.route('/update_role/<int:user_id>', methods=['POST'])
@login_required
def update_role(user_id):
    new_role = request.form.get('role')
    users = []
    with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'r', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 5:
                if int(row[0]) == user_id:
                    row[3] = new_role
                users.append(row)
    with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(users)
    return redirect(url_for('admin'))

@app.route('/update_status/<int:user_id>', methods=['POST'])
@login_required
def update_status(user_id):
    new_status = request.form.get('status')
    users = []
    with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'r', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 5:
                if int(row[0]) == user_id:
                    row[4] = new_status
                users.append(row)
    with open(os.path.join(USER_DATA_FOLDER, 'users.csv'), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(users)
    return redirect(url_for('admin'))


@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    users = []
    user_file_path = os.path.join(USER_DATA_FOLDER, 'users.csv')

    # Read the users.csv file
    with open(user_file_path, 'r', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 5 and int(row[0]) != user_id:
                users.append(row)

    # Write back to the users.csv file without the deleted user
    with open(user_file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(users)

    return redirect(url_for('admin'))


@app.route('/download/<path:filename>')
@login_required
def download_file(filename):
    return send_from_directory(DATA_FOLDER, filename, as_attachment=True)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html'), 404

if __name__ == '__main__':
    # Charger les données GeoJSON
    geojson_file_path = 'data/departements.geojson'
    departements_geo = gpd.read_file(geojson_file_path)

    # Charger les données CSV
    file_path_dep = 'data/donnee-dep-data.gouv-2023-geographie2023-produit-le2024-03-07.csv'
    file_path_nom = 'data/departements-france.csv'

    df_dep = pd.read_csv(file_path_dep, header=None, sep=';', engine='python')
    df_nom = pd.read_csv(file_path_nom, header=None, sep=',', engine='python')

    df_dep.columns = df_dep.iloc[0]
    df_dep = df_dep[1:]

    df_nom.columns = df_nom.iloc[0]
    df_nom = df_nom[1:]


    def format_departement(dept):
        if isinstance(dept, int) and dept < 10:
            return f"0{dept}"
        return dept

    df_dep['Code.département'] = df_dep['Code.département'].apply(format_departement)

    # Adjusting merge based on actual column names
    departements_data = df_dep.merge(df_nom, how="inner", left_on="Code.département", right_on="code_departement")

    # Convertir les colonnes de fusion en chaînes de caractères pour assurer la compatibilité
    departements_geo['code'] = departements_geo['code'].astype(str)
    departements_data['code_departement'] = departements_data['code_departement'].astype(str)

    # Nettoyer et convertir la colonne tauxpourmille en numérique
    departements_data['tauxpourmille'] = pd.to_numeric(departements_data['tauxpourmille'].str.replace(',', '.'),
                                                       errors='coerce').fillna(0)
    app.run(debug=True)
