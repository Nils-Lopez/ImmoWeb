#!/usr/bin/env python3
"""FlatSwipe — A personal Tinder-like flat search tool for ImmoWeb."""

import sqlite3
import json
import datetime
import threading
import time
import random
import os

from flask import Flask, request, jsonify, send_from_directory

DATABASE = './flatswipe.sqlite'
PIC_DOWNLOAD_DIR = './static/img_cache'

app = Flask(__name__, static_folder='static')

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            min_price INTEGER DEFAULT 0,
            max_price INTEGER DEFAULT 500000,
            postal_codes TEXT DEFAULT '',
            last_scrape TEXT
        );

        CREATE TABLE IF NOT EXISTS flats (
            id INTEGER PRIMARY KEY,
            title TEXT,
            description TEXT,
            price INTEGER,
            price_old INTEGER,
            surface INTEGER,
            land_surface INTEGER,
            bedrooms INTEGER,
            bathrooms INTEGER,
            parking INTEGER,
            living_room INTEGER,
            condition TEXT,
            construction_year TEXT,
            epc_score TEXT,
            energy_consumption REAL,
            postal_code TEXT,
            city TEXT,
            street TEXT,
            number TEXT,
            type TEXT,
            subtype TEXT,
            url TEXT,
            picture_urls TEXT DEFAULT '',
            picture_downloads TEXT DEFAULT '',
            status TEXT DEFAULT 'unseen',
            created_at TEXT,
            last_modified TEXT,
            provider TEXT DEFAULT 'immoweb'
        );

        CREATE INDEX IF NOT EXISTS idx_flats_status ON flats(status);

        INSERT OR IGNORE INTO config (id) VALUES (1);
    ''')
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------------------
# API — Config
# ---------------------------------------------------------------------------

@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    row = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    return jsonify({
        'min_price': row['min_price'],
        'max_price': row['max_price'],
        'postal_codes': row['postal_codes'],
        'last_scrape': row['last_scrape'],
    })


@app.route('/api/config', methods=['POST'])
def save_config():
    data = request.json
    conn = get_db()
    conn.execute('''
        UPDATE config SET min_price = ?, max_price = ?, postal_codes = ? WHERE id = 1
    ''', (data.get('min_price', 0), data.get('max_price', 500000), data.get('postal_codes', '')))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API — Flats
# ---------------------------------------------------------------------------

@app.route('/api/flats/unseen', methods=['GET'])
def get_unseen():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM flats WHERE status = ? ORDER BY last_modified DESC',
        ('unseen',)
    ).fetchall()
    conn.close()
    return jsonify([_flat_to_dict(r) for r in rows])


@app.route('/api/flats/liked', methods=['GET'])
def get_liked():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM flats WHERE status = ? ORDER BY last_modified DESC',
        ('liked',)
    ).fetchall()
    conn.close()
    return jsonify([_flat_to_dict(r) for r in rows])


@app.route('/api/flats/masked', methods=['GET'])
def get_masked():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM flats WHERE status = ? ORDER BY last_modified DESC',
        ('masked',)
    ).fetchall()
    conn.close()
    return jsonify([_flat_to_dict(r) for r in rows])


@app.route('/api/flats/<int:flat_id>/action', methods=['POST'])
def flat_action(flat_id):
    data = request.json
    action = data.get('action')  # 'liked' or 'masked'
    if action not in ('liked', 'masked', 'unseen'):
        return jsonify({'error': 'Invalid action'}), 400
    conn = get_db()
    conn.execute('UPDATE flats SET status = ? WHERE id = ?', (action, flat_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    unseen = conn.execute('SELECT COUNT(*) as c FROM flats WHERE status = ?', ('unseen',)).fetchone()['c']
    liked = conn.execute('SELECT COUNT(*) as c FROM flats WHERE status = ?', ('liked',)).fetchone()['c']
    masked = conn.execute('SELECT COUNT(*) as c FROM flats WHERE status = ?', ('masked',)).fetchone()['c']
    conn.close()
    return jsonify({'unseen': unseen, 'liked': liked, 'masked': masked})


# ---------------------------------------------------------------------------
# API — Scraping
# ---------------------------------------------------------------------------

scrape_status = {'running': False, 'progress': '', 'count': 0}


@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    if scrape_status['running']:
        return jsonify({'error': 'Scrape already running'}), 409

    thread = threading.Thread(target=_run_scrape, daemon=True)
    thread.start()
    return jsonify({'ok': True, 'message': 'Scraping started'})


@app.route('/api/scrape/status', methods=['GET'])
def scrape_progress():
    return jsonify(scrape_status)


def _build_search_url(config_row):
    """Build an ImmoWeb search URL from config."""
    base = 'https://www.immoweb.be/nl/zoeken/huis/te-koop'
    params = ['countries=BE']
    if config_row['postal_codes']:
        codes = config_row['postal_codes'].replace(' ', '')
        params.append(f'postalCodes={codes}')
    if config_row['min_price']:
        params.append(f'minPrice={config_row["min_price"]}')
    if config_row['max_price']:
        params.append(f'maxPrice={config_row["max_price"]}')
    params.append('orderBy=newest')
    return base + '?' + '&'.join(params)


def _run_scrape():
    from ImmoCollecterImmoWeb import ImmoWeb

    scrape_status['running'] = True
    scrape_status['progress'] = 'Starting...'
    scrape_status['count'] = 0

    try:
        conn = get_db()
        config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
        existing_ids = set(r['id'] for r in conn.execute('SELECT id FROM flats').fetchall())
        conn.close()

        search_url = _build_search_url(config)
        scrape_status['progress'] = 'Fetching listings...'

        immo = ImmoWeb(search_url)
        house_list = immo.get_list_all_houses()
        scrape_status['progress'] = f'Found {len(house_list)} listings, fetching details...'

        new_count = 0
        for i, house in enumerate(house_list):
            house_id = house.get('id')
            if house_id in existing_ids:
                continue

            scrape_status['progress'] = f'Processing {i+1}/{len(house_list)}...'
            time.sleep(random.uniform(2, 5))

            try:
                details = immo.get_house_details(house)
                if details is None:
                    continue
                _save_flat(details)
                new_count += 1
                scrape_status['count'] = new_count
            except Exception as e:
                print(f'Error scraping {house_id}: {e}')

        conn = get_db()
        conn.execute('UPDATE config SET last_scrape = ? WHERE id = 1',
                     (datetime.datetime.now().isoformat(),))
        conn.commit()
        conn.close()

        scrape_status['progress'] = f'Done! Added {new_count} new flats.'
    except Exception as e:
        scrape_status['progress'] = f'Error: {str(e)}'
        print(f'Scrape error: {e}')
    finally:
        scrape_status['running'] = False


def _save_flat(details):
    conn = get_db()
    conn.execute('''
        INSERT OR IGNORE INTO flats
        (id, title, description, price, price_old, surface, land_surface,
         bedrooms, bathrooms, parking, living_room, condition, construction_year,
         epc_score, energy_consumption, postal_code, city, street, number,
         type, subtype, url, picture_urls, picture_downloads, status,
         created_at, last_modified, provider)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unseen', ?, ?, ?)
    ''', (
        details.get('id'),
        details.get('title', ''),
        details.get('description', ''),
        details.get('price_main'),
        details.get('price_old'),
        details.get('surface'),
        details.get('landSurface'),
        details.get('bedrooms'),
        details.get('bathrooms'),
        details.get('parking'),
        details.get('livingRoom'),
        details.get('condition'),
        details.get('constructionYear'),
        details.get('epcScore'),
        details.get('primaryEnergyConsumptionPerSqm'),
        details.get('postalcode'),
        details.get('city'),
        details.get('street'),
        details.get('number'),
        details.get('type'),
        details.get('subtype'),
        details.get('url'),
        details.get('pictureUrls', ''),
        details.get('pictureUrls', ''),
        details.get('creationDate', datetime.datetime.now().isoformat()),
        details.get('lastModificationDate', datetime.datetime.now().isoformat()),
        details.get('immoProvider', 'immoweb'),
    ))
    conn.commit()
    conn.close()


def _flat_to_dict(row):
    pics = row['picture_urls'].split(',') if row['picture_urls'] else []
    # Use ImmoWeb CDN URLs directly (no local download needed)
    return {
        'id': row['id'],
        'title': row['title'],
        'description': row['description'],
        'price': row['price'],
        'price_old': row['price_old'],
        'surface': row['surface'],
        'land_surface': row['land_surface'],
        'bedrooms': row['bedrooms'],
        'bathrooms': row['bathrooms'],
        'parking': row['parking'],
        'living_room': row['living_room'],
        'condition': row['condition'],
        'construction_year': row['construction_year'],
        'epc_score': row['epc_score'],
        'energy_consumption': row['energy_consumption'],
        'postal_code': row['postal_code'],
        'city': row['city'],
        'street': row['street'],
        'number': row['number'],
        'type': row['type'],
        'subtype': row['subtype'],
        'url': row['url'],
        'pictures': [p.strip() for p in pics if p.strip()],
        'status': row['status'],
        'provider': row['provider'],
    }


# ---------------------------------------------------------------------------
# API — Seed data (for testing when proxy blocks ImmoWeb)
# ---------------------------------------------------------------------------

SAMPLE_PICS = [
    'https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800',
    'https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800',
    'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800',
    'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=800',
]

@app.route('/api/seed', methods=['POST'])
def seed_data():
    """Insert realistic sample flats for testing the UI."""
    samples = [
        {'id': 90001, 'title': 'Charmante woning met tuin in Gent', 'description': 'Prachtige gezinswoning met ruime living, 3 slaapkamers en een zonnige tuin. Rustig gelegen nabij het stadscentrum met alle voorzieningen in de buurt. Recent gerenoveerde keuken en badkamer.', 'price': 385000, 'surface': 165, 'land_surface': 450, 'bedrooms': 3, 'bathrooms': 1, 'parking': 1, 'epc_score': 'C', 'postal_code': '9000', 'city': 'Gent', 'street': 'Coupure', 'number': '42', 'subtype': 'HOUSE', 'condition': 'GOOD', 'construction_year': '1985', 'pictures': SAMPLE_PICS[:3]},
        {'id': 90002, 'title': 'Moderne villa met zwembad in Aalst', 'description': 'Luxueuze villa met open keuken, 4 slaapkamers, dubbele garage en verwarmd zwembad. Energiezuinig met zonnepanelen. Prachtig aangelegde tuin van 800m\u00B2.', 'price': 625000, 'price_old': 650000, 'surface': 240, 'land_surface': 800, 'bedrooms': 4, 'bathrooms': 2, 'parking': 2, 'epc_score': 'A', 'postal_code': '9300', 'city': 'Aalst', 'street': 'Molenstraat', 'number': '15', 'subtype': 'VILLA', 'condition': 'AS_NEW', 'construction_year': '2018', 'pictures': SAMPLE_PICS},
        {'id': 90003, 'title': 'Gezellig rijhuis te Dendermonde', 'description': 'Instapklaar rijhuis met 2 slaapkamers, kleine stadstuin en fietsenstalling. Ideaal voor starters. Nabij station en winkels.', 'price': 245000, 'surface': 110, 'land_surface': 120, 'bedrooms': 2, 'bathrooms': 1, 'parking': 0, 'epc_score': 'D', 'postal_code': '9200', 'city': 'Dendermonde', 'street': 'Kerkstraat', 'number': '7', 'subtype': 'HOUSE', 'condition': 'GOOD', 'construction_year': '1960', 'pictures': SAMPLE_PICS[:2]},
        {'id': 90004, 'title': 'Ruime fermette met grond in Oudenaarde', 'description': 'Authentieke fermette op 1500m\u00B2 grond. 5 slaapkamers, grote schuur, stallingen. Te renoveren maar enorm potentieel. Prachtig landelijk uitzicht.', 'price': 320000, 'surface': 280, 'land_surface': 1500, 'bedrooms': 5, 'bathrooms': 1, 'parking': 3, 'epc_score': 'F', 'postal_code': '9700', 'city': 'Oudenaarde', 'street': 'Berchemweg', 'number': '89', 'subtype': 'FARMHOUSE', 'condition': 'TO_RENOVATE', 'construction_year': '1920', 'pictures': SAMPLE_PICS[1:]},
        {'id': 90005, 'title': 'Nieuwbouw appartement centrum Kortrijk', 'description': 'Lichtrijk nieuwbouwappartement met 2 slaapkamers, terras en ondergrondse parking. Lift aanwezig. Hoogwaardige afwerking met vloerverwarming.', 'price': 295000, 'surface': 95, 'land_surface': None, 'bedrooms': 2, 'bathrooms': 1, 'parking': 1, 'epc_score': 'A', 'postal_code': '8500', 'city': 'Kortrijk', 'street': 'Grote Markt', 'number': '3B', 'subtype': 'APARTMENT', 'condition': 'AS_NEW', 'construction_year': '2024', 'pictures': SAMPLE_PICS[:2]},
        {'id': 90006, 'title': 'Bel-etage met garage in Tielt', 'description': 'Ruime bel-etage met 3 slaapkamers, garage voor 2 wagens en onderhoudsvriendelijke tuin. Recente CV-ketel en dubbele beglazing.', 'price': 275000, 'surface': 155, 'land_surface': 350, 'bedrooms': 3, 'bathrooms': 1, 'parking': 2, 'epc_score': 'C', 'postal_code': '8700', 'city': 'Tielt', 'street': 'Ieperstraat', 'number': '22', 'subtype': 'HOUSE', 'condition': 'GOOD', 'construction_year': '1992', 'pictures': SAMPLE_PICS},
        {'id': 90007, 'title': 'Halfopen bebouwing aan de rand van Gent', 'description': 'Halfopen bebouwing met 4 slaapkamers en grote tuin. Gelegen in een kindvriendelijke buurt met goede verbinding naar het centrum. Mogelijkheid tot uitbreiding.', 'price': 425000, 'surface': 185, 'land_surface': 600, 'bedrooms': 4, 'bathrooms': 2, 'parking': 1, 'epc_score': 'B', 'postal_code': '9032', 'city': 'Wondelgem', 'street': 'Botestraat', 'number': '51', 'subtype': 'HOUSE', 'condition': 'GOOD', 'construction_year': '2005', 'pictures': SAMPLE_PICS[:3]},
        {'id': 90008, 'title': 'Studio in hartje Brussel', 'description': 'Compacte maar slimme studio nabij de Grote Markt. Ideaal als investering of pied-\u00E0-terre. Volledig gerenoveerd in 2023.', 'price': 175000, 'surface': 35, 'land_surface': None, 'bedrooms': 1, 'bathrooms': 1, 'parking': 0, 'epc_score': 'B', 'postal_code': '1000', 'city': 'Brussel', 'street': 'Rue du March\u00E9', 'number': '12', 'subtype': 'STUDIO', 'condition': 'AS_NEW', 'construction_year': '1890', 'pictures': SAMPLE_PICS[2:]},
    ]

    conn = get_db()
    for s in samples:
        pics = ','.join(s.get('pictures', []))
        conn.execute('''
            INSERT OR IGNORE INTO flats
            (id, title, description, price, price_old, surface, land_surface,
             bedrooms, bathrooms, parking, living_room, condition, construction_year,
             epc_score, energy_consumption, postal_code, city, street, number,
             type, subtype, url, picture_urls, picture_downloads, status,
             created_at, last_modified, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unseen', ?, ?, ?)
        ''', (
            s['id'], s['title'], s['description'], s['price'], s.get('price_old'),
            s['surface'], s.get('land_surface'), s['bedrooms'], s['bathrooms'],
            s['parking'], None, s.get('condition'), s.get('construction_year'),
            s.get('epc_score'), None, s['postal_code'], s['city'], s['street'],
            s['number'], 'HOUSE', s['subtype'],
            f'https://www.immoweb.be/nl/zoekertje/{s["id"]}', pics, pics,
            datetime.datetime.now().isoformat(), datetime.datetime.now().isoformat(),
            'immoweb',
        ))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'count': len(samples)})


# ---------------------------------------------------------------------------
# Serve the SPA
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')


@app.route('/frontend/<path:path>')
def serve_frontend(path):
    return send_from_directory('frontend', path)


if __name__ == '__main__':
    os.makedirs(PIC_DOWNLOAD_DIR, exist_ok=True)
    os.makedirs('frontend', exist_ok=True)
    app.run(debug=True, port=5000, host='0.0.0.0')
