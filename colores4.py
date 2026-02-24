#!/usr/bin/env python3
"""
ZOOLO CASINO LOCAL v2.1 — Layout Compacto
Animales izquierda | Controles derecha
Colores exactos por animal
"""

import os, json, csv, io, sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template_string, request, session, redirect, jsonify, Response
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'zoolo_local_2025_ultra_seguro')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zoolo_casino.db')

PAGO_ANIMAL_NORMAL = 35
PAGO_LECHUZA       = 70
PAGO_ESPECIAL      = 2
PAGO_TRIPLETA      = 60
COMISION_AGENCIA   = 0.15
MINUTOS_BLOQUEO    = 5

HORARIOS_PERU = [
    "08:00 AM","09:00 AM","10:00 AM","11:00 AM","12:00 PM",
    "01:00 PM","02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM"
]
HORARIOS_VENEZUELA = [
    "09:00 AM","10:00 AM","11:00 AM","12:00 PM","01:00 PM",
    "02:00 PM","03:00 PM","04:00 PM","05:00 PM","06:00 PM","07:00 PM"
]

ANIMALES = {
    "00":"Ballena","0":"Delfin","1":"Carnero","2":"Toro","3":"Ciempies",
    "4":"Alacran","5":"Leon","6":"Rana","7":"Perico","8":"Raton","9":"Aguila",
    "10":"Tigre","11":"Gato","12":"Caballo","13":"Mono","14":"Paloma",
    "15":"Zorro","16":"Oso","17":"Pavo","18":"Burro","19":"Chivo","20":"Cochino",
    "21":"Gallo","22":"Camello","23":"Cebra","24":"Iguana","25":"Gallina",
    "26":"Vaca","27":"Perro","28":"Zamuro","29":"Elefante","30":"Caiman",
    "31":"Lapa","32":"Ardilla","33":"Pescado","34":"Venado","35":"Jirafa",
    "36":"Culebra","37":"Aviapa","38":"Conejo","39":"Tortuga","40":"Lechuza"
}

# Color exacto por animal: verde=00,0 | rojo=1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36,37,39 | negro=resto | lechuza=40
COLORES = {
    "00":"verde","0":"verde",
    "1":"rojo","3":"rojo","5":"rojo","7":"rojo","9":"rojo",
    "12":"rojo","14":"rojo","16":"rojo","18":"rojo","19":"rojo",
    "21":"rojo","23":"rojo","25":"rojo","27":"rojo","30":"rojo",
    "32":"rojo","34":"rojo","36":"rojo","37":"rojo","39":"rojo",
    "40":"negro",
    "2":"negro","4":"negro","6":"negro","8":"negro","10":"negro","11":"negro",
    "13":"negro","15":"negro","17":"negro","20":"negro","22":"negro",
    "24":"negro","26":"negro","28":"negro","29":"negro","31":"negro",
    "33":"negro","35":"negro","38":"negro"
}

ROJOS = ["1","3","5","7","9","12","14","16","18","19",
         "21","23","25","27","30","32","34","36","37","39"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS agencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nombre_agencia TEXT NOT NULL,
            es_admin INTEGER DEFAULT 0,
            comision REAL DEFAULT 0.15,
            activa INTEGER DEFAULT 1,
            creado TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial TEXT UNIQUE NOT NULL,
            agencia_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL,
            pagado INTEGER DEFAULT 0,
            anulado INTEGER DEFAULT 0,
            creado TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agencia_id) REFERENCES agencias(id)
        );
        CREATE TABLE IF NOT EXISTS jugadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            hora TEXT NOT NULL,
            seleccion TEXT NOT NULL,
            monto REAL NOT NULL,
            tipo TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS tripletas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            animal1 TEXT NOT NULL,
            animal2 TEXT NOT NULL,
            animal3 TEXT NOT NULL,
            monto REAL NOT NULL,
            fecha TEXT NOT NULL,
            pagado INTEGER DEFAULT 0,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            animal TEXT NOT NULL,
            UNIQUE(fecha, hora)
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_agencia ON tickets(agencia_id);
        CREATE INDEX IF NOT EXISTS idx_tickets_fecha ON tickets(fecha);
        CREATE INDEX IF NOT EXISTS idx_jugadas_ticket ON jugadas(ticket_id);
        CREATE INDEX IF NOT EXISTS idx_tripletas_ticket ON tripletas(ticket_id);
        CREATE INDEX IF NOT EXISTS idx_resultados_fecha ON resultados(fecha);
        """)
        admin = db.execute("SELECT id FROM agencias WHERE es_admin=1").fetchone()
        if not admin:
            db.execute("INSERT INTO agencias (usuario,password,nombre_agencia,es_admin,comision,activa) VALUES (?,?,?,1,0,1)",
                       ('admin','admin123','ADMINISTRADOR'))
            db.commit()

def ahora_peru():
    return datetime.now(timezone.utc) - timedelta(hours=5)

def parse_fecha(f):
    if not f: return None
    for fmt in ("%d/%m/%Y %I:%M %p", "%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(f, fmt)
        except: pass
    return None

def generar_serial():
    return str(int(ahora_peru().timestamp() * 1000))

def fmt(m):
    try:
        v = float(m)
        return str(int(v)) if v == int(v) else str(v)
    except: return str(m)

def hora_a_min(h):
    try:
        p = h.replace(':',' ').split()
        hr, mn, ap = int(p[0]), int(p[1]), p[2]
        if ap=='PM' and hr!=12: hr+=12
        elif ap=='AM' and hr==12: hr=0
        return hr*60+mn
    except: return 0

def puede_vender(hora_sorteo):
    ahora = ahora_peru()
    diff = hora_a_min(hora_sorteo) - (ahora.hour*60+ahora.minute)
    return diff > MINUTOS_BLOQUEO

def calcular_premio_animal(monto, num):
    return monto * (PAGO_LECHUZA if str(num)=="40" else PAGO_ANIMAL_NORMAL)

def calcular_premio_ticket(ticket_id, db=None):
    close = False
    if db is None:
        db = get_db(); close = True
    try:
        t = db.execute("SELECT fecha FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not t: return 0
        fecha_ticket = parse_fecha(t['fecha'])
        if not fecha_ticket: return 0
        fecha_str = fecha_ticket.strftime("%d/%m/%Y")
        res_rows = db.execute("SELECT hora, animal FROM resultados WHERE fecha=?", (fecha_str,)).fetchall()
        resultados = {r['hora']: r['animal'] for r in res_rows}
        total = 0
        jugadas = db.execute("SELECT * FROM jugadas WHERE ticket_id=?", (ticket_id,)).fetchall()
        for j in jugadas:
            wa = resultados.get(j['hora'])
            if not wa: continue
            if j['tipo']=='animal' and str(wa)==str(j['seleccion']):
                total += calcular_premio_animal(j['monto'], wa)
            elif j['tipo']=='especial' and str(wa) not in ["0","00"]:
                sel, num = j['seleccion'], int(wa)
                if (sel=='ROJO' and str(wa) in ROJOS) or \
                   (sel=='NEGRO' and str(wa) not in ROJOS) or \
                   (sel=='PAR' and num%2==0) or \
                   (sel=='IMPAR' and num%2!=0):
                    total += j['monto'] * PAGO_ESPECIAL
        trips = db.execute("SELECT * FROM tripletas WHERE ticket_id=?", (ticket_id,)).fetchall()
        for tr in trips:
            nums = {tr['animal1'], tr['animal2'], tr['animal3']}
            salidos = {a for a in resultados.values() if a in nums}
            if len(salidos)==3:
                total += tr['monto'] * PAGO_TRIPLETA
        return total
    finally:
        if close: db.close()

def login_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect('/login')
        return f(*a,**k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session or not session.get('es_admin'):
            return "No autorizado", 403
        return f(*a,**k)
    return d

def agencia_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return jsonify({'error':'Login requerido'}),403
        if session.get('es_admin'): return jsonify({'error':'Admin no puede vender'}),403
        return f(*a,**k)
    return d

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/admin' if session.get('es_admin') else '/pos')
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    error=""
    if request.method=='POST':
        u = request.form.get('usuario','').strip().lower()
        p = request.form.get('password','').strip()
        with get_db() as db:
            row = db.execute("SELECT * FROM agencias WHERE usuario=? AND password=? AND activa=1",(u,p)).fetchone()
        if row:
            session['user_id'] = row['id']
            session['nombre_agencia'] = row['nombre_agencia']
            session['es_admin'] = bool(row['es_admin'])
            return redirect('/')
        error="Usuario o clave incorrecta"
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/pos')
@login_required
def pos():
    if session.get('es_admin'): return redirect('/admin')
    return render_template_string(POS_HTML,
        agencia=session['nombre_agencia'],
        animales=ANIMALES,
        colores=COLORES,
        horarios_peru=HORARIOS_PERU,
        horarios_venezuela=HORARIOS_VENEZUELA)

@app.route('/admin')
@admin_required
def admin():
    return render_template_string(ADMIN_HTML, animales=ANIMALES, horarios=HORARIOS_PERU)

# ========== API ==========
@app.route('/api/hora-actual')
@login_required
def hora_actual():
    ahora = ahora_peru()
    bloqueadas = [h for h in HORARIOS_PERU if not puede_vender(h)]
    return jsonify({'hora_str': ahora.strftime("%I:%M %p"), 'bloqueadas': bloqueadas})

@app.route('/api/resultados-hoy')
@login_required
def resultados_hoy():
    hoy = ahora_peru().strftime("%d/%m/%Y")
    with get_db() as db:
        rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=?",(hoy,)).fetchall()
    rd = {r['hora']:{'animal':r['animal'],'nombre':ANIMALES.get(r['animal'],'?')} for r in rows}
    for h in HORARIOS_PERU:
        if h not in rd: rd[h]=None
    return jsonify({'status':'ok','fecha':hoy,'resultados':rd})

@app.route('/api/resultados-fecha', methods=['POST'])
@login_required
def resultados_fecha():
    data = request.get_json() or {}
    fs = data.get('fecha')
    try: fecha_obj = datetime.strptime(fs, "%Y-%m-%d") if fs else ahora_peru()
    except: fecha_obj = ahora_peru()
    fecha_str = fecha_obj.strftime("%d/%m/%Y")
    with get_db() as db:
        rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=?",(fecha_str,)).fetchall()
    rd = {r['hora']:{'animal':r['animal'],'nombre':ANIMALES.get(r['animal'],'?')} for r in rows}
    for h in HORARIOS_PERU:
        if h not in rd: rd[h]=None
    return jsonify({'status':'ok','fecha_consulta':fecha_str,'resultados':rd})

@app.route('/api/procesar-venta', methods=['POST'])
@agencia_required
def procesar_venta():
    try:
        data = request.get_json()
        jugadas = data.get('jugadas', [])
        if not jugadas: return jsonify({'error':'Ticket vacío'}),400
        for j in jugadas:
            if j['tipo']!='tripleta' and not puede_vender(j['hora']):
                return jsonify({'error':f"Sorteo {j['hora']} ya cerró"}),400
        serial = generar_serial()
        fecha  = ahora_peru().strftime("%d/%m/%Y %I:%M %p")
        total  = sum(j['monto'] for j in jugadas)
        with get_db() as db:
            cur = db.execute("INSERT INTO tickets (serial,agencia_id,fecha,total) VALUES (?,?,?,?)",
                (serial, session['user_id'], fecha, total))
            ticket_id = cur.lastrowid
            for j in jugadas:
                if j['tipo']=='tripleta':
                    nums = j['seleccion'].split(',')
                    db.execute("INSERT INTO tripletas (ticket_id,animal1,animal2,animal3,monto,fecha) VALUES (?,?,?,?,?,?)",
                        (ticket_id, nums[0], nums[1], nums[2], j['monto'], fecha.split(' ')[0]))
                else:
                    db.execute("INSERT INTO jugadas (ticket_id,hora,seleccion,monto,tipo) VALUES (?,?,?,?,?)",
                        (ticket_id, j['hora'], j['seleccion'], j['monto'], j['tipo']))
            db.commit()
        jpoh = defaultdict(list)
        for j in jugadas:
            if j['tipo']!='tripleta': jpoh[j['hora']].append(j)
        lineas = [f"*{session['nombre_agencia']}*",
                  f"*TICKET:* #{ticket_id}",
                  f"*SERIAL:* {serial}", fecha,
                  "------------------------",""]
        for hp in HORARIOS_PERU:
            if hp not in jpoh: continue
            idx = HORARIOS_PERU.index(hp)
            hv  = HORARIOS_VENEZUELA[idx]
            hpc = hp.replace(' ','').replace('00','').lower()
            hvc = hv.replace(' ','').replace('00','').lower()
            lineas.append(f"*ZOOLO.PERU/{hpc}...VZLA/{hvc}*")
            items=[]
            for j in jpoh[hp]:
                if j['tipo']=='animal':
                    n = ANIMALES.get(j['seleccion'],'')[0:3].upper()
                    items.append(f"{n}{j['seleccion']}x{fmt(j['monto'])}")
                else:
                    items.append(f"{j['seleccion'][0:3]}x{fmt(j['monto'])}")
            lineas.append(" ".join(items)); lineas.append("")
        trips_t = [j for j in jugadas if j['tipo']=='tripleta']
        if trips_t:
            lineas.append("*TRIPLETAS (Paga x60)*")
            for t in trips_t:
                nums = t['seleccion'].split(',')
                ns   = [ANIMALES.get(n,'')[0:3].upper() for n in nums]
                lineas.append(f"{'-'.join(ns)} x60 S/{fmt(t['monto'])}")
            lineas.append("")
        lineas += ["------------------------",f"*TOTAL: S/{fmt(total)}*","","Buena Suerte! 🍀","El ticket vence a los 3 dias"]
        import urllib.parse
        texto = "\n".join(lineas)
        url_wa = f"https://wa.me/?text={urllib.parse.quote(texto)}"
        return jsonify({'status':'ok','serial':serial,'ticket_id':ticket_id,'total':total,'url_whatsapp':url_wa})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/mis-tickets', methods=['POST'])
@agencia_required
def mis_tickets():
    try:
        data = request.get_json() or {}
        fi = data.get('fecha_inicio'); ff = data.get('fecha_fin'); est = data.get('estado','todos')
        dti = datetime.strptime(fi,"%Y-%m-%d") if fi else None
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59) if ff else None
        with get_db() as db:
            rows = db.execute("SELECT * FROM tickets WHERE agencia_id=? AND anulado=0 ORDER BY id DESC LIMIT 500",(session['user_id'],)).fetchall()
            resultado_cache = {}
            tickets_out = []
            for t in rows:
                dt = parse_fecha(t['fecha'])
                if not dt: continue
                if dti and dt<dti: continue
                if dtf and dt>dtf: continue
                if est=='pagados' and not t['pagado']: continue
                if est=='pendientes' and t['pagado']: continue
                fecha_str = dt.strftime("%d/%m/%Y")
                if fecha_str not in resultado_cache:
                    rr = db.execute("SELECT hora,animal FROM resultados WHERE fecha=?",(fecha_str,)).fetchall()
                    resultado_cache[fecha_str] = {r['hora']:r['animal'] for r in rr}
                res_dia = resultado_cache[fecha_str]
                jugadas_raw = db.execute("SELECT * FROM jugadas WHERE ticket_id=?",(t['id'],)).fetchall()
                tripletas_raw = db.execute("SELECT * FROM tripletas WHERE ticket_id=?",(t['id'],)).fetchall()
                premio_total = 0
                jugadas_det = []
                for j in jugadas_raw:
                    wa = res_dia.get(j['hora']); gano=False; pj=0
                    if wa:
                        if j['tipo']=='animal' and str(wa)==str(j['seleccion']):
                            pj=calcular_premio_animal(j['monto'],wa); gano=True
                        elif j['tipo']=='especial' and str(wa) not in ["0","00"]:
                            sel,num=j['seleccion'],int(wa)
                            if (sel=='ROJO' and str(wa) in ROJOS) or (sel=='NEGRO' and str(wa) not in ROJOS) or (sel=='PAR' and num%2==0) or (sel=='IMPAR' and num%2!=0):
                                pj=j['monto']*PAGO_ESPECIAL; gano=True
                    if gano: premio_total+=pj
                    jugadas_det.append({'tipo':j['tipo'],'hora':j['hora'],'seleccion':j['seleccion'],
                        'nombre':ANIMALES.get(j['seleccion'],j['seleccion']) if j['tipo']=='animal' else j['seleccion'],
                        'monto':j['monto'],'resultado':wa,
                        'resultado_nombre':ANIMALES.get(str(wa),str(wa)) if wa else None,
                        'gano':gano,'premio':round(pj,2)})
                trips_det = []
                for tr in tripletas_raw:
                    nums={tr['animal1'],tr['animal2'],tr['animal3']}
                    salidos=list(dict.fromkeys([a for a in res_dia.values() if a in nums]))
                    gano_t=len(salidos)==3; pt=tr['monto']*PAGO_TRIPLETA if gano_t else 0
                    if gano_t: premio_total+=pt
                    trips_det.append({'animal1':tr['animal1'],'nombre1':ANIMALES.get(tr['animal1'],tr['animal1']),
                        'animal2':tr['animal2'],'nombre2':ANIMALES.get(tr['animal2'],tr['animal2']),
                        'animal3':tr['animal3'],'nombre3':ANIMALES.get(tr['animal3'],tr['animal3']),
                        'monto':tr['monto'],'salieron':salidos,'gano':gano_t,'premio':round(pt,2),'pagado':bool(tr['pagado'])})
                if est=='por_pagar' and (t['pagado'] or premio_total==0): continue
                tickets_out.append({'id':t['id'],'serial':t['serial'],'fecha':t['fecha'],
                    'total':t['total'],'pagado':bool(t['pagado']),'premio_calculado':round(premio_total,2),
                    'jugadas':jugadas_det,'tripletas':trips_det})
        tv = sum(t['total'] for t in tickets_out)
        return jsonify({'status':'ok','tickets':tickets_out,'totales':{'cantidad':len(tickets_out),'ventas':round(tv,2)}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/consultar-ticket-detalle', methods=['POST'])
@login_required
def consultar_ticket_detalle():
    try:
        serial = (request.get_json() or {}).get('serial')
        if not serial: return jsonify({'error':'Serial requerido'}),400
        with get_db() as db:
            if session.get('es_admin'):
                t = db.execute("SELECT * FROM tickets WHERE serial=?",(serial,)).fetchone()
            else:
                t = db.execute("SELECT * FROM tickets WHERE serial=? AND agencia_id=?",(serial,session['user_id'])).fetchone()
            if not t: return jsonify({'error':'Ticket no encontrado'})
            t = dict(t)
            fecha_str = parse_fecha(t['fecha']).strftime("%d/%m/%Y")
            res_rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=?",(fecha_str,)).fetchall()
            res_dia = {r['hora']:r['animal'] for r in res_rows}
            jugadas_raw = db.execute("SELECT * FROM jugadas WHERE ticket_id=?",(t['id'],)).fetchall()
            tripletas_raw = db.execute("SELECT * FROM tripletas WHERE ticket_id=?",(t['id'],)).fetchall()
        premio_total=0; jdet=[]
        for j in jugadas_raw:
            wa=res_dia.get(j['hora']); gano=False; pj=0
            if wa:
                if j['tipo']=='animal' and str(wa)==str(j['seleccion']):
                    pj=calcular_premio_animal(j['monto'],wa); gano=True
                elif j['tipo']=='especial' and str(wa) not in ["0","00"]:
                    sel,num=j['seleccion'],int(wa)
                    if (sel=='ROJO' and str(wa) in ROJOS) or (sel=='NEGRO' and str(wa) not in ROJOS) or (sel=='PAR' and num%2==0) or (sel=='IMPAR' and num%2!=0):
                        pj=j['monto']*PAGO_ESPECIAL; gano=True
            if gano: premio_total+=pj
            jdet.append({'tipo':j['tipo'],'hora':j['hora'],'seleccion':j['seleccion'],
                'nombre_seleccion':ANIMALES.get(j['seleccion'],j['seleccion']) if j['tipo']=='animal' else j['seleccion'],
                'monto':j['monto'],'resultado':wa,
                'resultado_nombre':ANIMALES.get(str(wa),str(wa)) if wa else None,
                'gano':gano,'premio':round(pj,2)})
        tdet=[]
        for tr in tripletas_raw:
            nums={tr['animal1'],tr['animal2'],tr['animal3']}
            salidos=list(dict.fromkeys([a for a in res_dia.values() if a in nums]))
            gano_t=len(salidos)==3; pt=tr['monto']*PAGO_TRIPLETA if gano_t else 0
            if gano_t: premio_total+=pt
            tdet.append({'tipo':'tripleta','animal1':tr['animal1'],'nombre1':ANIMALES.get(tr['animal1'],''),
                'animal2':tr['animal2'],'nombre2':ANIMALES.get(tr['animal2'],''),
                'animal3':tr['animal3'],'nombre3':ANIMALES.get(tr['animal3'],''),
                'monto':tr['monto'],'salieron':salidos,'gano':gano_t,'premio':round(pt,2),'pagado':bool(tr['pagado'])})
        return jsonify({'status':'ok',
            'ticket':{'id':t['id'],'serial':t['serial'],'fecha':t['fecha'],
                'total_apostado':t['total'],'pagado':bool(t['pagado']),'anulado':bool(t['anulado']),'premio_total':round(premio_total,2)},
            'jugadas':jdet,'tripletas':tdet})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/verificar-ticket', methods=['POST'])
@login_required
def verificar_ticket():
    try:
        serial = request.json.get('serial')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=?",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            if t['anulado']: return jsonify({'error':'TICKET ANULADO'})
            if t['pagado']:  return jsonify({'error':'YA FUE PAGADO'})
            premio = calcular_premio_ticket(t['id'], db)
        return jsonify({'status':'ok','ticket_id':t['id'],'total_ganado':round(premio,2)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/pagar-ticket', methods=['POST'])
@login_required
def pagar_ticket():
    try:
        tid = request.json.get('ticket_id')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE id=?",(tid,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            db.execute("UPDATE tickets SET pagado=1 WHERE id=?",(tid,))
            db.execute("UPDATE tripletas SET pagado=1 WHERE ticket_id=?",(tid,))
            db.commit()
        return jsonify({'status':'ok','mensaje':'Ticket pagado'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/anular-ticket', methods=['POST'])
@login_required
def anular_ticket():
    try:
        serial = request.json.get('serial')
        with get_db() as db:
            t = db.execute("SELECT * FROM tickets WHERE serial=?",(serial,)).fetchone()
            if not t: return jsonify({'error':'Ticket no existe'})
            if not session.get('es_admin') and t['agencia_id']!=session['user_id']:
                return jsonify({'error':'No autorizado'})
            if t['pagado']: return jsonify({'error':'Ya pagado, no se puede anular'})
            if not session.get('es_admin'):
                dt = parse_fecha(t['fecha'])
                if dt and (ahora_peru()-dt).total_seconds()/60 > 5:
                    return jsonify({'error':'Solo puede anular dentro de 5 minutos'})
                jugs = db.execute("SELECT hora FROM jugadas WHERE ticket_id=?",(t['id'],)).fetchall()
                for j in jugs:
                    if not puede_vender(j['hora']):
                        return jsonify({'error':f"Sorteo {j['hora']} ya cerró"})
            db.execute("UPDATE tickets SET anulado=1 WHERE id=?",(t['id'],))
            db.commit()
        return jsonify({'status':'ok','mensaje':'Ticket anulado correctamente'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/caja')
@agencia_required
def caja_agencia():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            tickets = db.execute("SELECT * FROM tickets WHERE agencia_id=? AND anulado=0 AND fecha LIKE ?",(session['user_id'], hoy+'%')).fetchall()
            ag = db.execute("SELECT comision FROM agencias WHERE id=?",(session['user_id'],)).fetchone()
            com_pct = ag['comision'] if ag else COMISION_AGENCIA
            ventas=0; premios_pagados=0; pendientes=0
            for t in tickets:
                ventas += t['total']
                p = calcular_premio_ticket(t['id'],db)
                if t['pagado']: premios_pagados+=p
                elif p>0: pendientes+=1
        return jsonify({'ventas':round(ventas,2),'premios':round(premios_pagados,2),
            'comision':round(ventas*com_pct,2),'balance':round(ventas-premios_pagados-ventas*com_pct,2),
            'tickets_pendientes':pendientes,'total_tickets':len(tickets)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/caja-historico', methods=['POST'])
@agencia_required
def caja_historico():
    try:
        data = request.get_json()
        fi,ff = data.get('fecha_inicio'), data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        dti = datetime.strptime(fi,"%Y-%m-%d")
        dtf = datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        with get_db() as db:
            ag = db.execute("SELECT comision FROM agencias WHERE id=?",(session['user_id'],)).fetchone()
            com_pct = ag['comision'] if ag else COMISION_AGENCIA
            tickets = db.execute("SELECT * FROM tickets WHERE agencia_id=? AND anulado=0 ORDER BY id DESC LIMIT 2000",(session['user_id'],)).fetchall()
        dias={}; tv=0; tp=0
        for t in tickets:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            dk=dt.strftime("%d/%m/%Y")
            if dk not in dias: dias[dk]={'ventas':0,'tickets':0,'premios':0}
            dias[dk]['ventas']+=t['total']; dias[dk]['tickets']+=1; tv+=t['total']
            with get_db() as db2: p=calcular_premio_ticket(t['id'],db2)
            if t['pagado']: dias[dk]['premios']+=p; tp+=p
        resumen=[]
        for dk in sorted(dias.keys()):
            d=dias[dk]; cd=d['ventas']*com_pct
            resumen.append({'fecha':dk,'tickets':d['tickets'],'ventas':round(d['ventas'],2),
                'premios':round(d['premios'],2),'comision':round(cd,2),'balance':round(d['ventas']-d['premios']-cd,2)})
        tc=tv*com_pct
        return jsonify({'resumen_por_dia':resumen,
            'totales':{'ventas':round(tv,2),'premios':round(tp,2),'comision':round(tc,2),'balance':round(tv-tp-tc,2)}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/guardar-resultado', methods=['POST'])
@admin_required
def guardar_resultado():
    try:
        hora = request.form.get('hora','').strip()
        animal = request.form.get('animal','').strip()
        fi = request.form.get('fecha','').strip()
        if animal not in ANIMALES: return jsonify({'error':f'Animal inválido'}),400
        if fi:
            try: fecha = datetime.strptime(fi,"%Y-%m-%d").strftime("%d/%m/%Y")
            except: fecha = ahora_peru().strftime("%d/%m/%Y")
        else:
            fecha = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            db.execute("INSERT INTO resultados (fecha,hora,animal) VALUES (?,?,?) ON CONFLICT(fecha,hora) DO UPDATE SET animal=excluded.animal",(fecha, hora, animal))
            db.commit()
        return jsonify({'status':'ok','mensaje':f'Resultado: {hora} = {animal} ({ANIMALES[animal]})','fecha':fecha})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/resultados-fecha-admin', methods=['POST'])
@admin_required
def resultados_fecha_admin():
    data = request.get_json() or {}
    fs = data.get('fecha')
    try: fecha_str = datetime.strptime(fs,"%Y-%m-%d").strftime("%d/%m/%Y")
    except: fecha_str = ahora_peru().strftime("%d/%m/%Y")
    with get_db() as db:
        rows = db.execute("SELECT hora,animal FROM resultados WHERE fecha=?",(fecha_str,)).fetchall()
    rd={r['hora']:{'animal':r['animal'],'nombre':ANIMALES.get(r['animal'],'?')} for r in rows}
    for h in HORARIOS_PERU:
        if h not in rd: rd[h]=None
    return jsonify({'status':'ok','fecha_consulta':fecha_str,'resultados':rd})

@app.route('/admin/lista-agencias')
@admin_required
def lista_agencias():
    with get_db() as db:
        rows = db.execute("SELECT id,usuario,nombre_agencia,comision,activa FROM agencias WHERE es_admin=0").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/admin/crear-agencia', methods=['POST'])
@admin_required
def crear_agencia():
    try:
        u = request.form.get('usuario','').strip().lower()
        p = request.form.get('password','').strip()
        n = request.form.get('nombre','').strip()
        if not u or not p or not n: return jsonify({'error':'Complete todos los campos'}),400
        with get_db() as db:
            ex = db.execute("SELECT id FROM agencias WHERE usuario=?",(u,)).fetchone()
            if ex: return jsonify({'error':'Usuario ya existe'}),400
            db.execute("INSERT INTO agencias (usuario,password,nombre_agencia,es_admin,comision,activa) VALUES (?,?,?,0,?,1)",(u,p,n,COMISION_AGENCIA))
            db.commit()
        return jsonify({'status':'ok','mensaje':f'Agencia {n} creada'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/editar-agencia', methods=['POST'])
@admin_required
def editar_agencia():
    try:
        data = request.get_json() or {}
        aid = data.get('id')
        with get_db() as db:
            if 'password' in data and data['password']:
                db.execute("UPDATE agencias SET password=? WHERE id=? AND es_admin=0",(data['password'],aid))
            if 'comision' in data:
                db.execute("UPDATE agencias SET comision=? WHERE id=? AND es_admin=0",(float(data['comision'])/100,aid))
            if 'activa' in data:
                db.execute("UPDATE agencias SET activa=? WHERE id=? AND es_admin=0",(1 if data['activa'] else 0,aid))
            db.commit()
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/reporte-agencias')
@admin_required
def reporte_agencias():
    try:
        hoy = ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            ags = db.execute("SELECT * FROM agencias WHERE es_admin=0").fetchall()
            tickets = db.execute("SELECT * FROM tickets WHERE anulado=0 AND fecha LIKE ?",(hoy+'%',)).fetchall()
        data=[]; tv=tp=tc=0
        for ag in ags:
            mts=[t for t in tickets if t['agencia_id']==ag['id']]
            ventas=sum(t['total'] for t in mts); pp=0
            for t in mts:
                with get_db() as db2: p=calcular_premio_ticket(t['id'],db2)
                if t['pagado']: pp+=p
            com=ventas*ag['comision']
            data.append({'nombre':ag['nombre_agencia'],'usuario':ag['usuario'],'ventas':round(ventas,2),
                'premios_pagados':round(pp,2),'comision':round(com,2),'balance':round(ventas-pp-com,2),'tickets':len(mts)})
            tv+=ventas; tp+=pp; tc+=com
        return jsonify({'agencias':data,'global':{'ventas':round(tv,2),'pagos':round(tp,2),'comisiones':round(tc,2),'balance':round(tv-tp-tc,2)}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/riesgo')
@admin_required
def riesgo():
    try:
        hoy=ahora_peru().strftime("%d/%m/%Y")
        now=ahora_peru(); am=now.hour*60+now.minute
        sorteo=None
        for h in HORARIOS_PERU:
            m=hora_a_min(h)
            if am>=m and am<m+60: sorteo=h; break
        if not sorteo:
            for h in HORARIOS_PERU:
                if (hora_a_min(h)-am)>MINUTOS_BLOQUEO: sorteo=h; break
        if not sorteo: sorteo=HORARIOS_PERU[-1]
        with get_db() as db:
            tickets=db.execute("SELECT id FROM tickets WHERE anulado=0 AND fecha LIKE ?",(hoy+'%',)).fetchall()
        apuestas={}; total=0
        for t in tickets:
            with get_db() as db:
                jugs=db.execute("SELECT * FROM jugadas WHERE ticket_id=? AND tipo='animal' AND hora=?",(t['id'],sorteo)).fetchall()
            for j in jugs:
                apuestas[j['seleccion']]=apuestas.get(j['seleccion'],0)+j['monto']; total+=j['monto']
        riesgo_d={}
        for sel,monto in sorted(apuestas.items(),key=lambda x:x[1],reverse=True):
            mult=PAGO_LECHUZA if sel=="40" else PAGO_ANIMAL_NORMAL
            riesgo_d[f"{sel} - {ANIMALES.get(sel,sel)}"]={'apostado':round(monto,2),'pagaria':round(monto*mult,2),'es_lechuza':sel=="40",'porcentaje':round(monto/total*100,1) if total>0 else 0}
        return jsonify({'riesgo':riesgo_d,'sorteo_objetivo':sorteo,'total_apostado':round(total,2)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/tripletas-hoy')
@admin_required
def tripletas_hoy():
    try:
        hoy=ahora_peru().strftime("%d/%m/%Y")
        with get_db() as db:
            trips=db.execute("SELECT tr.*,tk.serial,tk.agencia_id FROM tripletas tr JOIN tickets tk ON tr.ticket_id=tk.id WHERE tr.fecha=?",(hoy,)).fetchall()
            res_rows=db.execute("SELECT hora,animal FROM resultados WHERE fecha=?",(hoy,)).fetchall()
            res_dia={r['hora']:r['animal'] for r in res_rows}
            ags={ag['id']:ag['nombre_agencia'] for ag in db.execute("SELECT id,nombre_agencia FROM agencias").fetchall()}
        out=[]; ganadoras=0
        for tr in trips:
            nums={tr['animal1'],tr['animal2'],tr['animal3']}
            salidos=list(dict.fromkeys([a for a in res_dia.values() if a in nums]))
            gano=len(salidos)==3
            if gano: ganadoras+=1
            out.append({'id':tr['id'],'serial':tr['serial'],'agencia':ags.get(tr['agencia_id'],'?'),
                'animal1':tr['animal1'],'animal2':tr['animal2'],'animal3':tr['animal3'],
                'nombres':[ANIMALES.get(tr['animal1'],''),ANIMALES.get(tr['animal2'],''),ANIMALES.get(tr['animal3'],'')],
                'monto':tr['monto'],'premio':tr['monto']*PAGO_TRIPLETA if gano else 0,'gano':gano,'salieron':salidos,'pagado':bool(tr['pagado'])})
        return jsonify({'tripletas':out,'total':len(out),'ganadoras':ganadoras,'total_premios':sum(x['premio'] for x in out)})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/exportar-csv', methods=['POST'])
@admin_required
def exportar_csv():
    try:
        data=request.get_json(); fi=data.get('fecha_inicio'); ff=data.get('fecha_fin')
        dti=datetime.strptime(fi,"%Y-%m-%d"); dtf=datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        with get_db() as db:
            ags=db.execute("SELECT * FROM agencias WHERE es_admin=0").fetchall()
            all_t=db.execute("SELECT * FROM tickets WHERE anulado=0 ORDER BY id DESC LIMIT 50000").fetchall()
        stats={ag['id']:{'nombre':ag['nombre_agencia'],'usuario':ag['usuario'],'tickets':0,'ventas':0,'premios':0,'comision_pct':ag['comision']} for ag in ags}
        for t in all_t:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            aid=t['agencia_id']
            if aid not in stats: continue
            stats[aid]['tickets']+=1; stats[aid]['ventas']+=t['total']
            if t['pagado']:
                with get_db() as db2: stats[aid]['premios']+=calcular_premio_ticket(t['id'],db2)
        out=io.StringIO(); w=csv.writer(out)
        w.writerow(['REPORTE ZOOLO CASINO']); w.writerow([f'Periodo: {fi} al {ff}']); w.writerow([])
        w.writerow(['Agencia','Usuario','Tickets','Ventas','Premios','Comision','Balance'])
        tv=0
        for s in sorted(stats.values(),key=lambda x:x['ventas'],reverse=True):
            if s['tickets']==0: continue
            com=s['ventas']*s['comision_pct']
            w.writerow([s['nombre'],s['usuario'],s['tickets'],round(s['ventas'],2),round(s['premios'],2),round(com,2),round(s['ventas']-s['premios']-com,2)])
            tv+=s['ventas']
        w.writerow([]); w.writerow(['TOTAL','',sum(s['tickets'] for s in stats.values()),round(tv,2),'','',''])
        out.seek(0)
        return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=reporte_{fi}_{ff}.csv'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

# ===================== HTML =====================

LOGIN_HTML = '''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZOOLO CASINO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050a12;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Rajdhani',sans-serif}
.box{background:#0a1020;padding:44px 36px;border-radius:6px;border:1px solid #1e3060;width:100%;max-width:400px;text-align:center;box-shadow:0 0 60px rgba(0,80,200,.1)}
.logo{font-family:'Oswald',sans-serif;font-size:2.6rem;font-weight:700;color:#fff;letter-spacing:4px;margin-bottom:4px}
.logo em{color:#f5a623;font-style:normal}
.sub{color:#3a5080;font-size:.8rem;letter-spacing:3px;margin-bottom:36px}
.fg{margin-bottom:18px;text-align:left}
.fg label{display:block;color:#3a5080;font-size:.78rem;letter-spacing:2px;margin-bottom:6px}
.fg input{width:100%;padding:13px 16px;background:#060e1e;border:1px solid #1e3060;border-radius:4px;color:#7ab0ff;font-size:.95rem;font-family:'Rajdhani',sans-serif;letter-spacing:1px}
.fg input:focus{outline:none;border-color:#2060d0;box-shadow:0 0 16px rgba(32,96,208,.15)}
.btn{width:100%;padding:15px;background:linear-gradient(135deg,#1a4cd0,#0d32a0);color:#fff;border:none;border-radius:4px;font-size:.95rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:3px;cursor:pointer;margin-top:8px;transition:all .3s}
.btn:hover{background:linear-gradient(135deg,#2060e8,#1440c0);box-shadow:0 6px 20px rgba(20,64,200,.3)}
.err{background:rgba(200,40,40,.1);color:#e05050;padding:11px;border-radius:4px;margin-bottom:16px;border:1px solid rgba(200,40,40,.2);font-size:.85rem}
</style></head><body>
<div class="box">
<div class="logo">ZOO<em>LO</em></div>
<div class="sub">SISTEMA DE APUESTAS</div>
{% if error %}<div class="err">⚠ {{error}}</div>{% endif %}
<form method="POST">
<div class="fg"><label>USUARIO</label><input type="text" name="usuario" required autofocus autocomplete="off"></div>
<div class="fg"><label>CONTRASEÑA</label><input type="password" name="password" required></div>
<button type="submit" class="btn">INGRESAR</button>
</form>
</div></body></html>'''


POS_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1,user-scalable=no">
<title>{{agencia}} — POS</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#06090f;--panel:#0a0e18;--card:#0d1220;--border:#1a2540;
  --gold:#f5a623;--blue:#2060d0;--teal:#00b4d8;
  --red:#e53e3e;--red-bg:#1a0808;--red-border:#6b1515;
  --negro:#2a3a5a;--negro-bg:#080c18;--negro-border:#1a2a4a;
  --verde:#16a34a;--verde-bg:#051209;--verde-border:#0d4d1e;
  --green:#22c55e;--orange:#f97316;--purple:#a855f7;
  --text:#c8d8f0;--text2:#4a6090;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;user-select:none}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:14px;display:flex;flex-direction:column}

/* ===== TOPBAR ===== */
.topbar{background:var(--panel);border-bottom:2px solid var(--border);padding:0 10px;height:36px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;letter-spacing:2px;color:#fff}
.brand em{color:var(--gold);font-style:normal}
.agent-name{color:var(--text2);font-size:.78rem;letter-spacing:1px;margin-left:10px}
.top-right{display:flex;align-items:center;gap:6px}
.clock{color:var(--gold);font-family:'Oswald',sans-serif;font-size:.85rem;letter-spacing:1px}
.tbtn{padding:4px 10px;border:1px solid var(--border);background:var(--card);color:var(--text2);border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Rajdhani',sans-serif;font-weight:600;letter-spacing:1px;transition:all .2s;white-space:nowrap}
.tbtn:hover{border-color:var(--teal);color:var(--teal)}
.tbtn.exit{border-color:#6b1515;color:#e05050}
.tbtn.exit:hover{background:var(--red-bg)}

/* ===== LAYOUT PRINCIPAL ===== */
.layout{display:flex;flex:1;overflow:hidden;gap:0}

/* ===== PANEL IZQUIERDO — ANIMALES ===== */
.left-panel{display:flex;flex-direction:column;width:62%;border-right:2px solid var(--border);overflow:hidden}

/* Especiales arriba */
.especiales-bar{display:flex;gap:4px;padding:5px 6px;background:var(--panel);border-bottom:1px solid var(--border);flex-shrink:0}
.esp-btn{flex:1;padding:7px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.78rem;font-weight:700;letter-spacing:1px;border:2px solid transparent;transition:all .2s}
.esp-btn.rojo{background:#1a0a0a;border-color:#8b2020;color:#e05050}
.esp-btn.rojo.sel,  .esp-btn.rojo:hover{background:#3a0d0d;border-color:var(--red);color:#ff6b6b}
.esp-btn.negro{background:#0a0e18;border-color:#1a2a5a;color:#6080c0}
.esp-btn.negro.sel, .esp-btn.negro:hover{background:#0d1530;border-color:var(--blue);color:#90b0ff}
.esp-btn.par{background:#050e10;border-color:#0a4050;color:#00a0b4}
.esp-btn.par.sel,   .esp-btn.par:hover{background:#051418;border-color:var(--teal);color:#00d4f8}
.esp-btn.impar{background:#100a18;border-color:#4a1a80;color:#9060d0}
.esp-btn.impar.sel, .esp-btn.impar:hover{background:#180d28;border-color:var(--purple);color:#c080ff}

/* Grid animales */
.animals-scroll{flex:1;overflow-y:auto;padding:4px 5px}
.animals-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}

/* Celda animal */
.acard{border-radius:4px;padding:3px 2px 2px;text-align:center;cursor:pointer;transition:all .12s;border:2px solid transparent;position:relative;overflow:hidden}
.acard:active{transform:scale(.92)}

/* VERDE */
.acard.cv{background:#051209;border-color:#0d4d1e}
.acard.cv .anum{color:#4ade80}
.acard.cv .anom{color:#166534}
.acard.cv:hover{background:#071a0e;border-color:#16a34a}
.acard.cv.sel{background:#0a2e14;border-color:var(--green);box-shadow:0 0 8px rgba(34,197,94,.3)}

/* ROJO */
.acard.cr{background:#1a0808;border-color:#6b1515}
.acard.cr .anum{color:#f87171}
.acard.cr .anom{color:#7f1d1d}
.acard.cr:hover{background:#220d0d;border-color:var(--red)}
.acard.cr.sel{background:#2d1010;border-color:#ef4444;box-shadow:0 0 8px rgba(239,68,68,.3)}

/* NEGRO */
.acard.cn{background:#080c18;border-color:#1a2540}
.acard.cn .anum{color:#93c5fd}
.acard.cn .anom{color:#1e3a5f}
.acard.cn:hover{background:#0c1228;border-color:#2060c0}
.acard.cn.sel{background:#0e1a38;border-color:var(--blue);box-shadow:0 0 8px rgba(32,96,208,.3)}

/* LECHUZA (40) negro especial */
.acard.cl{background:#100c04;border-color:#4a3a08}
.acard.cl .anum{color:#fbbf24}
.acard.cl .anom{color:#78470a}
.acard.cl:hover{background:#180e04;border-color:var(--gold)}
.acard.cl.sel{background:#201206;border-color:var(--gold);box-shadow:0 0 10px rgba(245,166,35,.3)}

.acard.sel::after{content:'✓';position:absolute;top:0;right:2px;font-size:.55rem;color:rgba(255,255,255,.8);font-weight:700}
.anum{font-size:.85rem;font-weight:700;font-family:'Oswald',sans-serif;line-height:1}
.anom{font-size:.52rem;line-height:1;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ===== PANEL DERECHO — CONTROLES ===== */
.right-panel{width:38%;display:flex;flex-direction:column;overflow-y:auto;background:var(--panel)}

/* SECCION */
.rsec{padding:5px 8px;border-bottom:1px solid var(--border)}
.rlabel{font-family:'Oswald',sans-serif;font-size:.65rem;font-weight:600;color:var(--text2);letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}

/* HORARIOS */
.horas-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:3px}
.hbtn{padding:5px 2px;text-align:center;background:var(--card);border:1px solid var(--border);border-radius:3px;cursor:pointer;font-size:.68rem;font-family:'Oswald',sans-serif;color:var(--text2);transition:all .2s;line-height:1.2}
.hbtn.sel{background:#0a1828;border-color:var(--teal);color:var(--teal)}
.hbtn.bloq{opacity:.3;cursor:not-allowed;text-decoration:line-through}
.hbtn .hperu{font-size:.65rem;font-weight:600}
.hbtn .hven{font-size:.55rem;color:var(--text2)}
.hbtn.sel .hven{color:#005570}
.horas-btns-row{display:flex;gap:3px;margin-top:3px}
.hsel-btn{flex:1;padding:3px;font-size:.62rem;background:transparent;border:1px solid var(--border);color:var(--text2);border-radius:3px;cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:600;letter-spacing:1px;text-align:center}
.hsel-btn:hover{border-color:var(--teal);color:var(--teal)}

/* TRIPLETA */
.trip-sec{padding:5px 8px;border-bottom:1px solid var(--border)}
.trip-label{font-family:'Oswald',sans-serif;font-size:.65rem;color:var(--purple);letter-spacing:2px;margin-bottom:4px}
.trip-slots{display:flex;gap:3px;margin-bottom:4px}
.tslot{flex:1;background:var(--card);border:1px solid #3a1a60;border-radius:3px;padding:4px 2px;text-align:center;cursor:pointer;min-height:36px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.tslot.act{border-color:var(--purple);box-shadow:0 0 8px rgba(168,85,247,.2)}
.tslot.fill{border-color:#7c3aed;background:#120a20}
.tslot .snum{font-size:.72rem;font-weight:700;font-family:'Oswald',sans-serif;color:#c084fc}
.tslot .snom{font-size:.55rem;color:#7c3aed}
.tslot .sph{font-size:.6rem;color:#3a2060;letter-spacing:1px}
.trip-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;max-height:80px;overflow-y:auto}
.trip-grid .acard{padding:2px 1px}
.trip-grid .anum{font-size:.72rem}
.trip-grid .anom{font-size:.48rem}

/* MONTO */
.monto-sec{padding:5px 8px;border-bottom:1px solid var(--border)}
.presets{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:4px}
.mpre{padding:5px 8px;background:var(--card);border:1px solid var(--border);border-radius:3px;color:var(--text2);cursor:pointer;font-size:.75rem;font-family:'Oswald',sans-serif;font-weight:600;transition:all .2s}
.mpre:hover,.mpre:active{background:#0a1828;border-color:var(--teal);color:var(--teal)}
.monto-input-wrap{display:flex;align-items:center;gap:4px}
.monto-label{color:var(--text2);font-size:.72rem;letter-spacing:1px;white-space:nowrap}
.monto-input{flex:1;padding:7px 8px;background:#060e1e;border:1px solid var(--border);border-radius:3px;color:var(--gold);font-size:1rem;font-family:'Oswald',sans-serif;font-weight:700;text-align:center;letter-spacing:1px}
.monto-input:focus{outline:none;border-color:var(--gold)}

/* TICKET */
.ticket-sec{padding:4px 8px;border-bottom:1px solid var(--border);flex:1;display:flex;flex-direction:column;min-height:0}
.ticket-list{flex:1;overflow-y:auto;min-height:40px}
.ti{display:flex;align-items:center;gap:3px;padding:3px 4px;border-bottom:1px solid #0a1020;font-size:.72rem}
.ti-desc{flex:1;color:#90a8d0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ti-hora{color:var(--teal);font-size:.65rem;min-width:38px;font-family:'Oswald',sans-serif}
.ti-monto{color:var(--green);font-weight:700;font-family:'Oswald',sans-serif;min-width:32px;text-align:right}
.ti-del{background:transparent;border:none;color:#6b1515;cursor:pointer;font-size:.7rem;padding:0 2px;line-height:1}
.ti-del:hover{color:var(--red)}
.ticket-empty{color:#1e2a40;text-align:center;padding:8px;font-size:.72rem;letter-spacing:2px}
.ticket-total{text-align:right;padding:4px 0 2px;font-family:'Oswald',sans-serif;color:var(--gold);font-size:.95rem;font-weight:700;letter-spacing:1px;border-top:1px solid var(--border)}

/* BOTONES ACCION */
.actions-sec{padding:5px 8px;display:flex;flex-direction:column;gap:3px;flex-shrink:0}
.btn-add{width:100%;padding:8px;background:linear-gradient(135deg,#0d2a60,#091d48);color:#7ab0ff;border:1px solid #1a3a80;border-radius:4px;font-family:'Oswald',sans-serif;font-weight:700;font-size:.8rem;letter-spacing:2px;cursor:pointer;transition:all .2s}
.btn-add:hover{background:linear-gradient(135deg,#1240a0,#0d2a70);color:#aad0ff}
.btn-wa{width:100%;padding:8px;background:linear-gradient(135deg,#064020,#042a14);color:#4ade80;border:1px solid #0d5a2a;border-radius:4px;font-family:'Oswald',sans-serif;font-weight:700;font-size:.8rem;letter-spacing:2px;cursor:pointer;transition:all .2s}
.btn-wa:hover{background:linear-gradient(135deg,#0a5c2a,#063c18)}
.btn-wa:disabled{opacity:.5;cursor:not-allowed}
.btns-row{display:grid;grid-template-columns:1fr 1fr;gap:3px}
.btns-row2{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px}
.abtn{padding:7px 4px;text-align:center;border-radius:4px;cursor:pointer;font-family:'Oswald',sans-serif;font-size:.68rem;font-weight:700;letter-spacing:1px;border:1px solid var(--border);background:var(--card);color:var(--text2);transition:all .2s;white-space:nowrap}
.abtn:hover{border-color:var(--teal);color:var(--teal)}
.abtn.res{border-color:#0a4050;color:var(--teal)}
.abtn.caja{border-color:#0d4d1e;color:var(--green)}
.abtn.pagar{border-color:#805010;color:var(--gold)}
.abtn.trip{border-color:#4a1a80;color:var(--purple)}
.abtn.anular{border-color:#6b1515;color:#e05050}
.abtn.borrar{border-color:#3a2010;color:#c06030}
.abtn.salir{border-color:#6b1515;color:#e05050;background:var(--red-bg)}

/* MODALES */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:1000;overflow-y:auto;padding:8px;align-items:flex-start;justify-content:center}
.modal.open{display:flex}
.mc{background:#080e1c;border:1px solid var(--border);border-radius:6px;width:100%;max-width:600px;margin:auto;overflow:hidden}
.mh{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);background:#060a14}
.mh h3{font-family:'Oswald',sans-serif;color:var(--teal);font-size:.9rem;letter-spacing:2px}
.mbody{padding:14px 16px}
.btn-close{background:transparent;color:var(--text2);border:1px solid var(--border);border-radius:3px;padding:4px 10px;cursor:pointer;font-size:.78rem}
.btn-close:hover{color:#fff}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.frow input,.frow select{flex:1;min-width:110px;padding:8px 10px;background:#060e1e;border:1px solid var(--border);border-radius:3px;color:var(--gold);font-family:'Rajdhani',sans-serif;font-size:.85rem}
.frow input:focus,.frow select:focus{outline:none;border-color:var(--teal)}
.btn-q{width:100%;padding:10px;background:linear-gradient(135deg,#0d2a60,#091d48);color:#7ab0ff;border:1px solid #1a3a80;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:2px;cursor:pointer;margin-bottom:8px;font-size:.8rem}
.ri{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;margin:4px 0;background:#060a14;border-radius:3px;border-left:2px solid #1a2540;font-size:.82rem}
.ri.ok{border-left-color:var(--green)}
.ri-hora{color:var(--gold);font-weight:700;font-family:'Oswald',sans-serif;font-size:.82rem}
.ri-animal{color:var(--green);font-weight:600}
.tcard{background:#060a14;padding:10px;margin:5px 0;border-radius:4px;border-left:2px solid #1a2540;font-size:.8rem}
.tcard.gano{border-left-color:var(--green)}
.tcard.pte{border-left-color:#c08020}
.ts{color:var(--teal);font-weight:700;font-family:'Oswald',sans-serif}
.badge{display:inline-block;padding:2px 7px;border-radius:3px;font-size:.68rem;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:1px}
.badge.p{background:#0a2a14;color:var(--green);border:1px solid #0d5a2a}
.badge.g{background:#3a2a08;color:var(--gold);border:1px solid #8a5a0a}
.badge.n{background:#0a0e18;color:var(--text2);border:1px solid var(--border)}
.jrow{display:flex;justify-content:space-between;align-items:center;padding:5px 8px;margin:2px 0;border-radius:3px;background:#050810;border-left:2px solid #1a2540;font-size:.78rem}
.jrow.gano{background:rgba(34,197,94,.06);border-left-color:var(--green)}
.sbox{background:#060a14;border-radius:3px;padding:10px;margin:6px 0;border:1px solid var(--border)}
.srow{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #0a0e18;font-size:.8rem}
.srow:last-child{border-bottom:none}
.sl{color:var(--text2)}.sv{color:var(--gold);font-weight:700;font-family:'Oswald',sans-serif}
.caja-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.cg{background:#060a14;border:1px solid var(--border);border-radius:3px;padding:12px;text-align:center}
.cgl{color:var(--text2);font-size:.68rem;letter-spacing:2px;margin-bottom:4px}
.cgv{color:var(--gold);font-size:1.1rem;font-weight:700;font-family:'Oswald',sans-serif}
.cgv.g{color:var(--green)}.cgv.r{color:var(--red)}

/* TOAST */
.toast{position:fixed;bottom:60px;left:50%;transform:translateX(-50%);padding:10px 18px;border-radius:4px;z-index:9999;font-size:.8rem;display:none;max-width:90%;font-family:'Oswald',sans-serif;letter-spacing:1px;text-align:center;border:1px solid}
.toast.ok{background:#062012;color:var(--green);border-color:#0d5a2a}
.toast.err{background:#140608;color:var(--red);border-color:#6b1515}

/* SCROLL */
::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:#050810}
::-webkit-scrollbar-thumb{background:#1a2540;border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:var(--blue)}

/* RESPONSIVE MOBILE */
@media(max-width:599px){
  html,body{overflow:auto}
  .layout{flex-direction:column}
  .left-panel{width:100%;border-right:none;border-bottom:2px solid var(--border);max-height:60vh}
  .right-panel{width:100%}
  .animals-grid{grid-template-columns:repeat(7,1fr)}
  .topbar .agent-name{display:none}
}
@media(min-width:600px) and (max-width:900px){
  .animals-grid{grid-template-columns:repeat(7,1fr)}
}
</style></head><body>

<!-- TOPBAR -->
<div class="topbar">
  <div style="display:flex;align-items:center">
    <div class="brand">ZOO<em>LO</em></div>
    <div class="agent-name">{{agencia}}</div>
  </div>
  <div class="top-right">
    <div class="clock" id="clock">--:--</div>
    <button class="tbtn" onclick="openMod('mod-consultas')">📋 Consultas</button>
    <button class="tbtn" onclick="openMod('mod-archivo')">📁 Archivo</button>
    <button class="tbtn exit" onclick="location.href='/logout'">SALIR</button>
  </div>
</div>

<!-- LAYOUT -->
<div class="layout">

  <!-- ===== IZQUIERDA: ESPECIALES + ANIMALES ===== -->
  <div class="left-panel">

    <!-- ESPECIALES -->
    <div class="especiales-bar">
      <div class="esp-btn rojo" id="esp-ROJO" onclick="selEsp('ROJO')">ROJO</div>
      <div class="esp-btn negro" id="esp-NEGRO" onclick="selEsp('NEGRO')">NEGRO</div>
      <div class="esp-btn par" id="esp-PAR" onclick="selEsp('PAR')">PAR</div>
      <div class="esp-btn impar" id="esp-IMPAR" onclick="selEsp('IMPAR')">IMPAR</div>
    </div>

    <!-- GRID ANIMALES -->
    <div class="animals-scroll">
      <div class="animals-grid" id="animals-grid"></div>
    </div>

  </div>

  <!-- ===== DERECHA: CONTROLES ===== -->
  <div class="right-panel">

    <!-- HORARIOS -->
    <div class="rsec">
      <div class="rlabel">⏰ Horarios</div>
      <div class="horas-grid" id="horas-grid"></div>
      <div class="horas-btns-row">
        <button class="hsel-btn" onclick="selTodos()">☑ Todos</button>
        <button class="hsel-btn" onclick="limpiarH()">✕ Limpiar</button>
      </div>
    </div>

    <!-- TRIPLETA -->
    <div class="trip-sec">
      <div class="trip-label">🎯 TRIPLETA x60 (todo el día)</div>
      <div class="trip-slots">
        <div class="tslot act" id="ts0" onclick="activarSlot(0)"><div class="sph">ANM 1</div></div>
        <div class="tslot" id="ts1" onclick="activarSlot(1)"><div class="sph">ANM 2</div></div>
        <div class="tslot" id="ts2" onclick="activarSlot(2)"><div class="sph">ANM 3</div></div>
      </div>
      <div class="trip-grid" id="trip-grid"></div>
    </div>

    <!-- MONTO -->
    <div class="monto-sec">
      <div class="presets">
        <button class="mpre" onclick="setM(.5)">0.5</button>
        <button class="mpre" onclick="setM(1)">1</button>
        <button class="mpre" onclick="setM(2)">2</button>
        <button class="mpre" onclick="setM(5)">5</button>
        <button class="mpre" onclick="setM(10)">10</button>
        <button class="mpre" onclick="setM(20)">20</button>
        <button class="mpre" onclick="setM(50)">50</button>
      </div>
      <div class="monto-input-wrap">
        <span class="monto-label">S/</span>
        <input type="number" class="monto-input" id="monto" value="1" min="0.5" step="0.5">
      </div>
    </div>

    <!-- TICKET -->
    <div class="ticket-sec">
      <div class="rlabel">🎫 TICKET</div>
      <div class="ticket-list" id="ticket-list">
        <div class="ticket-empty">TICKET VACÍO</div>
      </div>
      <div id="ticket-total" style="display:none" class="ticket-total"></div>
    </div>

    <!-- BOTONES ACCIÓN -->
    <div class="actions-sec">
      <button class="btn-add" onclick="agregar()">➕ AGREGAR AL TICKET</button>
      <button class="btn-wa" onclick="vender()" id="btn-wa" disabled>📤 ENVIAR POR WHATSAPP</button>
      <div class="btns-row">
        <div class="abtn res" onclick="openResultados()">📊 RESULTADOS</div>
        <div class="abtn caja" onclick="openCaja()">💰 CAJA</div>
      </div>
      <div class="btns-row">
        <div class="abtn pagar" onclick="openPagar()">💵 PAGAR</div>
        <div class="abtn anular" onclick="openAnular()">❌ ANULAR</div>
      </div>
      <div class="btns-row2">
        <div class="abtn trip" onclick="openMod('mod-trip-modal')">🎯 TRIPLETA</div>
        <div class="abtn borrar" onclick="borrarTodo()">🗑 BORRAR</div>
        <div class="abtn salir" onclick="location.href='/logout'">🚪 SALIR</div>
      </div>
    </div>

  </div>
</div><!-- /layout -->

<div class="toast" id="toast"></div>

<!-- ====== MODALES ====== -->

<!-- RESULTADOS -->
<div class="modal" id="mod-resultados">
<div class="mc">
  <div class="mh"><h3>📊 RESULTADOS</h3><button class="btn-close" onclick="closeMod('mod-resultados')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="date" id="res-fecha"></div>
    <button class="btn-q" onclick="cargarResultados()">VER RESULTADOS</button>
    <div id="res-titulo" style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;text-align:center;margin-bottom:8px;font-size:.8rem"></div>
    <div id="res-lista" style="max-height:340px;overflow-y:auto"></div>
  </div>
</div></div>

<!-- CONSULTAS (tickets) -->
<div class="modal" id="mod-consultas">
<div class="mc">
  <div class="mh"><h3>📋 CONSULTAS</h3><button class="btn-close" onclick="closeMod('mod-consultas')">✕</button></div>
  <div class="mbody">
    <div class="frow">
      <input type="date" id="mt-ini">
      <input type="date" id="mt-fin">
      <select id="mt-estado">
        <option value="todos">Todos</option>
        <option value="pagados">Pagados</option>
        <option value="pendientes">Pendientes</option>
        <option value="por_pagar">Con Premio</option>
      </select>
    </div>
    <button class="btn-q" onclick="consultarTickets()">BUSCAR</button>
    <div id="mt-resumen" style="display:none;background:rgba(0,180,216,.06);border:1px solid #0a4050;border-radius:3px;padding:8px;margin-bottom:8px;color:var(--teal);font-size:.78rem;font-family:'Oswald',sans-serif;letter-spacing:1px"></div>
    <div id="mt-lista" style="max-height:400px;overflow-y:auto">
      <p style="color:var(--text2);text-align:center;padding:20px;letter-spacing:2px;font-size:.75rem">USE LOS FILTROS Y BUSQUE</p>
    </div>
  </div>
</div></div>

<!-- ARCHIVO -->
<div class="modal" id="mod-archivo">
<div class="mc">
  <div class="mh"><h3>📁 ARCHIVO — CAJA HISTÓRICO</h3><button class="btn-close" onclick="closeMod('mod-archivo')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="date" id="ar-ini"><input type="date" id="ar-fin"></div>
    <button class="btn-q" onclick="cajaHist()">VER HISTÓRICO</button>
    <div id="ar-res"></div>
  </div>
</div></div>

<!-- BUSCAR/PAGAR -->
<div class="modal" id="mod-pagar">
<div class="mc">
  <div class="mh"><h3>💵 VERIFICAR / PAGAR</h3><button class="btn-close" onclick="closeMod('mod-pagar')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="text" id="pag-serial" placeholder="Serial del ticket"></div>
    <button class="btn-q" onclick="verificarTicket()">VERIFICAR</button>
    <div id="pag-res"></div>
  </div>
</div></div>

<!-- ANULAR -->
<div class="modal" id="mod-anular">
<div class="mc">
  <div class="mh"><h3>❌ ANULAR TICKET</h3><button class="btn-close" onclick="closeMod('mod-anular')">✕</button></div>
  <div class="mbody">
    <div class="frow"><input type="text" id="an-serial" placeholder="Serial del ticket"></div>
    <button class="btn-q" style="background:linear-gradient(135deg,#3a1010,#280808);border-color:#6b1515;color:#e05050" onclick="anularTicket()">ANULAR</button>
    <div id="an-res"></div>
  </div>
</div></div>

<!-- CAJA HOY -->
<div class="modal" id="mod-caja">
<div class="mc">
  <div class="mh"><h3>💰 CAJA HOY</h3><button class="btn-close" onclick="closeMod('mod-caja')">✕</button></div>
  <div class="mbody" id="caja-body"></div>
</div></div>

<!-- TRIPLETA MODAL (solo info) -->
<div class="modal" id="mod-trip-modal">
<div class="mc">
  <div class="mh"><h3>🎯 TRIPLETA x60</h3><button class="btn-close" onclick="closeMod('mod-trip-modal')">✕</button></div>
  <div class="mbody">
    <p style="color:var(--text2);font-size:.82rem;margin-bottom:12px">Selecciona los 3 animales directamente en el panel izquierdo usando los slots de la sección TRIPLETA.</p>
    <div style="background:#0a0e18;border:1px solid #3a1a80;border-radius:4px;padding:12px;font-size:.82rem">
      <div style="color:var(--purple);font-family:'Oswald',sans-serif;margin-bottom:6px">¿CÓMO JUGAR TRIPLETA?</div>
      <div style="color:var(--text2);line-height:1.7">1. Haz clic en Slot 1, Slot 2 o Slot 3 para activarlo<br>2. Toca un animal en la fila de tripleta para asignarlo<br>3. Ingresa el monto<br>4. Presiona AGREGAR AL TICKET</div>
    </div>
  </div>
</div></div>

<script>
const ANIMALES = {{ animales | tojson }};
const COLORES  = {{ colores | tojson }};
const HPERU = {{ horarios_peru | tojson }};
const HVEN  = {{ horarios_venezuela | tojson }};
const ROJOS = ["1","3","5","7","9","12","14","16","18","19","21","23","25","27","30","32","34","36","37","39"];
const ORDEN = ['00','0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','25','26','27','28','29','30','31','32','33','34','35','36','37','38','39','40'];

let carrito = [];
let horasSel = [];
let animalesSel = [];
let espSel = null;
let tripSlot = 0;
let tripAnim = [null, null, null];
let horasBloq = [];
let modoTrip = false;

// ===== INIT =====
function init(){
  renderAnimales();
  renderTripGrid();
  renderHoras();
  actualizarBloq();
  setInterval(actualizarBloq, 30000);
  setInterval(actualizarClock, 1000);
  actualizarClock();
  let hoy = new Date().toISOString().split('T')[0];
  ['res-fecha','mt-ini','mt-fin','ar-ini','ar-fin'].forEach(id=>{
    let el=document.getElementById(id); if(el) el.value=hoy;
  });
}

function actualizarClock(){
  let now = new Date();
  // Ajuste a hora Perú (UTC-5)
  let peru = new Date(now.getTime() - (now.getTimezoneOffset()+300)*60000);
  let h = peru.getUTCHours(), m = peru.getUTCMinutes();
  let ap = h>=12?'PM':'AM'; h = h%12||12;
  document.getElementById('clock').textContent = `${h}:${String(m).padStart(2,'0')} ${ap}`;
}

function actualizarBloq(){
  fetch('/api/hora-actual').then(r=>r.json()).then(d=>{
    horasBloq = d.bloqueadas||[];
    horasSel = horasSel.filter(h=>!horasBloq.includes(h));
    renderHoras();
  }).catch(()=>{});
}

// ===== COLORES =====
function getCardClass(k){
  if(k==='40') return 'cl';
  let c = COLORES[k];
  if(c==='verde') return 'cv';
  if(c==='rojo')  return 'cr';
  return 'cn';
}

// ===== ANIMALES =====
function renderAnimales(){
  let g = document.getElementById('animals-grid');
  g.innerHTML = '';
  ORDEN.forEach(k=>{
    if(!ANIMALES[k]) return;
    let d = document.createElement('div');
    d.className = `acard ${getCardClass(k)}`;
    d.dataset.k = k;
    d.innerHTML = `<div class="anum">${k}</div><div class="anom">${ANIMALES[k]}</div>`;
    d.onclick = ()=>toggleAnimal(k,d);
    g.appendChild(d);
  });
}

function toggleAnimal(k, el){
  let i = animalesSel.indexOf(k);
  if(i>=0){ animalesSel.splice(i,1); el.classList.remove('sel'); }
  else { animalesSel.push(k); el.classList.add('sel'); }
}

// ===== ESPECIALES =====
function selEsp(v){
  if(espSel===v){ espSel=null; document.getElementById('esp-'+v).classList.remove('sel'); }
  else {
    if(espSel) document.getElementById('esp-'+espSel).classList.remove('sel');
    espSel=v;
    // Deseleccionar animales
    animalesSel=[]; document.querySelectorAll('.animals-grid .acard').forEach(c=>c.classList.remove('sel'));
    document.getElementById('esp-'+v).classList.add('sel');
  }
}

// ===== HORARIOS =====
function renderHoras(){
  let g = document.getElementById('horas-grid'); g.innerHTML='';
  HPERU.forEach((h,i)=>{
    let b = document.createElement('div');
    b.className = 'hbtn';
    let bloq = horasBloq.includes(h);
    let sel = horasSel.includes(h);
    if(bloq) b.classList.add('bloq');
    if(sel) b.classList.add('sel');
    let hp = h.replace(':00',''); let hv = HVEN[i].replace(':00','');
    b.innerHTML = `<div class="hperu">${hp}</div><div class="hven">VE:${hv}</div>`;
    if(!bloq) b.onclick = ()=>toggleH(h);
    g.appendChild(b);
  });
}
function toggleH(h){ let i=horasSel.indexOf(h); if(i>=0) horasSel.splice(i,1); else horasSel.push(h); renderHoras(); }
function selTodos(){ horasSel=HPERU.filter(h=>!horasBloq.includes(h)); renderHoras(); }
function limpiarH(){ horasSel=[]; renderHoras(); }

// ===== TRIPLETA =====
function renderTripGrid(){
  let g = document.getElementById('trip-grid'); g.innerHTML='';
  ORDEN.forEach(k=>{
    if(!ANIMALES[k]) return;
    let d = document.createElement('div');
    d.className = `acard ${getCardClass(k)}`;
    d.innerHTML = `<div class="anum">${k}</div><div class="anom">${ANIMALES[k]}</div>`;
    d.onclick = ()=>selTripAnim(k);
    g.appendChild(d);
  });
}

function activarSlot(i){ tripSlot=i; actualizarSlots(); }

function selTripAnim(k){
  let otro = tripAnim.findIndex((x,i)=>x===k && i!==tripSlot);
  if(otro>=0){ toast('Ya está en otro slot','err'); return; }
  tripAnim[tripSlot]=k;
  actualizarSlots();
  if(tripSlot<2) activarSlot(tripSlot+1);
}

function actualizarSlots(){
  for(let i=0;i<3;i++){
    let s=document.getElementById('ts'+i);
    let k=tripAnim[i];
    if(k){
      s.innerHTML=`<div class="snum">${k}</div><div class="snom">${ANIMALES[k].substring(0,5)}</div>`;
      s.classList.add('fill');
      s.className = `tslot fill${i===tripSlot?' act':''}`;
      s.onclick = ()=>{ tripAnim[i]=null; activarSlot(i); actualizarSlots(); };
    } else {
      s.innerHTML=`<div class="sph">ANM ${i+1}</div>`;
      s.className = `tslot${i===tripSlot?' act':''}`;
      s.onclick = ()=>activarSlot(i);
    }
  }
}

// ===== MONTO =====
function setM(v){ document.getElementById('monto').value=v; }

// ===== AGREGAR =====
function agregar(){
  let monto = parseFloat(document.getElementById('monto').value)||0;
  if(monto<=0){ toast('Monto inválido','err'); return; }

  // Tripleta: si los 3 slots están llenos
  if(tripAnim.every(x=>x!==null)){
    let sel=tripAnim.join(',');
    let desc=tripAnim.map(n=>n+'-'+ANIMALES[n].substring(0,4)).join(' ');
    carrito.push({tipo:'tripleta',hora:'TODO DÍA',seleccion:sel,monto,desc:'🎯 '+desc});
    tripAnim=[null,null,null]; tripSlot=0; actualizarSlots();
    renderCarrito(); toast('Tripleta agregada','ok'); return;
  }

  // Especial
  if(espSel){
    if(horasSel.length===0){ toast('Seleccione horario','err'); return; }
    horasSel.forEach(h=>{
      let labels={'ROJO':'🔴 ROJO','NEGRO':'⚫ NEGRO','PAR':'🔵 PAR','IMPAR':'🟡 IMPAR'};
      carrito.push({tipo:'especial',hora:h,seleccion:espSel,monto,desc:labels[espSel]+' x2'});
    });
    renderCarrito(); toast('Especial(es) agregado','ok'); return;
  }

  // Animal
  if(animalesSel.length===0){ toast('Seleccione animal(es)','err'); return; }
  if(horasSel.length===0){ toast('Seleccione horario(s)','err'); return; }
  horasSel.forEach(h=>{
    animalesSel.forEach(k=>{
      carrito.push({tipo:'animal',hora:h,seleccion:k,monto,desc:`${k}-${ANIMALES[k]}`});
    });
  });
  renderCarrito(); toast(`${animalesSel.length * horasSel.length} jugada(s) agregada(s)`,'ok');
}

// ===== CARRITO =====
function renderCarrito(){
  let list=document.getElementById('ticket-list');
  let tot=document.getElementById('ticket-total');
  document.getElementById('btn-wa').disabled = carrito.length===0;
  if(!carrito.length){
    list.innerHTML='<div class="ticket-empty">TICKET VACÍO</div>';
    tot.style.display='none'; return;
  }
  let html='', total=0;
  carrito.forEach((it,i)=>{
    total+=it.monto;
    let idx=HPERU.indexOf(it.hora);
    let hv=idx>=0?HVEN[idx]:'';
    let horaLabel=it.hora==='TODO DÍA'?'x60':it.hora.replace(':00','').replace(' ','');
    html+=`<div class="ti">
      <span class="ti-hora">${horaLabel}</span>
      <span class="ti-desc">${it.desc}</span>
      <span class="ti-monto">${it.monto}</span>
      <button class="ti-del" onclick="quitarItem(${i})">✕</button>
    </div>`;
  });
  list.innerHTML=html;
  tot.style.display='block';
  tot.textContent=`TOTAL: S/ ${total.toFixed(2)}`;
}

function quitarItem(i){ carrito.splice(i,1); renderCarrito(); }
function borrarTodo(){ carrito=[]; renderCarrito(); toast('Ticket borrado','err'); }

// ===== VENDER =====
async function vender(){
  if(!carrito.length){ toast('Ticket vacío','err'); return; }
  let btn=document.getElementById('btn-wa');
  btn.disabled=true; btn.textContent='⏳ PROCESANDO...';
  try{
    let r=await fetch('/api/procesar-venta',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({jugadas:carrito.map(c=>({hora:c.hora,seleccion:c.seleccion,monto:c.monto,tipo:c.tipo}))})});
    let d=await r.json();
    if(d.error){ toast(d.error,'err'); }
    else{
      window.open(d.url_whatsapp,'_blank');
      toast(`✅ Ticket #${d.ticket_id} generado!`,'ok');
      carrito=[]; renderCarrito();
    }
  }catch(e){ toast('Error de conexión','err'); }
  finally{ btn.disabled=false; btn.textContent='📤 ENVIAR POR WHATSAPP'; }
}

// ===== RESULTADOS =====
function openResultados(){ openMod('mod-resultados'); }
function cargarResultados(){
  let f=document.getElementById('res-fecha').value; if(!f)return;
  let c=document.getElementById('res-lista');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/api/resultados-fecha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f})})
  .then(r=>r.json()).then(d=>{
    let fd=new Date(f+'T00:00:00');
    document.getElementById('res-titulo').textContent=fd.toLocaleDateString('es-PE',{weekday:'long',day:'numeric',month:'long'}).toUpperCase();
    let html='';
    HPERU.forEach((h,i)=>{
      let res=d.resultados[h];
      let hv=HVEN[i];
      html+=`<div class="ri ${res?'ok':''}">
        <span class="ri-hora">${h.replace(':00','')} <span style="color:var(--text2);font-size:.65rem">/ ${hv.replace(':00','')}</span></span>
        ${res?`<span class="ri-animal">${res.animal} — ${res.nombre}</span>`:'<span style="color:#1e2a40;font-size:.78rem">PENDIENTE</span>'}
      </div>`;
    });
    c.innerHTML=html;
  }).catch(()=>{c.innerHTML='<p style="color:var(--red);text-align:center">Error</p>';});
}

// ===== CONSULTAS =====
function consultarTickets(){
  let ini=document.getElementById('mt-ini').value;
  let fin=document.getElementById('mt-fin').value;
  let est=document.getElementById('mt-estado').value;
  if(!ini||!fin){ toast('Seleccione fechas','err'); return; }
  let lista=document.getElementById('mt-lista');
  lista.innerHTML='<p style="color:var(--text2);text-align:center;padding:15px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/api/mis-tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin,estado:est})})
  .then(r=>r.json()).then(d=>{
    if(d.error){lista.innerHTML=`<p style="color:var(--red);text-align:center">${d.error}</p>`;return;}
    let res=document.getElementById('mt-resumen'); res.style.display='block';
    res.textContent=`${d.totales.cantidad} TICKET(S) — TOTAL: S/ ${d.totales.ventas.toFixed(2)}`;
    if(!d.tickets.length){lista.innerHTML='<p style="color:var(--text2);text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN RESULTADOS</p>';return;}
    let html='';
    d.tickets.forEach((t,idx)=>{
      let bc=t.pagado?'p':(t.premio_calculado>0?'g':'n');
      let bt=t.pagado?'✅ PAGADO':(t.premio_calculado>0?'🏆 GANADOR':'⏳ PENDIENTE');
      let tc=t.pagado?'gano':(t.premio_calculado>0?'pte':'');
      let jhtml='';
      if(t.jugadas) t.jugadas.forEach(j=>{
        let rn=j.resultado_nombre?(j.resultado+' — '+j.resultado_nombre):(j.resultado||'...');
        jhtml+=`<div class="jrow ${j.gano?'gano':''}">
          <span style="color:var(--teal);font-family:'Oswald',sans-serif;font-size:.72rem;min-width:55px">${j.hora.replace(':00','')}</span>
          <span style="flex:1;color:#90a8d0;overflow:hidden;text-overflow:ellipsis">${j.seleccion} ${j.nombre||''}</span>
          <span style="color:var(--text2);font-size:.72rem">S/${j.monto}</span>
          ${j.gano?`<span style="color:var(--green);font-weight:700;margin-left:4px;font-size:.72rem">+S/${j.premio}</span>`:''}
        </div>`;
      });
      html+=`<div class="tcard ${tc}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px">
          <div style="flex:1;min-width:0">
            <div class="ts">🎫 #${t.serial}</div>
            <div style="color:var(--text2);font-size:.7rem">${t.fecha}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <span class="badge ${bc}">${bt}</span>
            <div style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.85rem;margin-top:2px">S/${t.total}</div>
            ${t.premio_calculado>0?`<div style="color:var(--green);font-size:.8rem;font-weight:700">+S/${t.premio_calculado.toFixed(2)}</div>`:''}
          </div>
        </div>
        <div style="margin-top:6px">${jhtml}</div>
      </div>`;
    });
    lista.innerHTML=html;
  }).catch(()=>{lista.innerHTML='<p style="color:var(--red);text-align:center">Error</p>';});
}

// ===== ARCHIVO/CAJA HISTÓRICO =====
function cajaHist(){
  let ini=document.getElementById('ar-ini').value;
  let fin=document.getElementById('ar-fin').value;
  if(!ini||!fin){ toast('Seleccione fechas','err'); return; }
  let c=document.getElementById('ar-res');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:10px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/api/caja-historico',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})})
  .then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<p style="color:var(--red)">${d.error}</p>`;return;}
    let html='<div class="sbox">';
    d.resumen_por_dia.forEach(dia=>{
      let col=dia.balance>=0?'var(--green)':'var(--red)';
      html+=`<div class="srow">
        <span class="sl">${dia.fecha}</span>
        <span style="font-size:.72rem;color:var(--text2)">V:${dia.ventas}</span>
        <span class="sv" style="color:${col}">S/${dia.balance.toFixed(2)}</span>
      </div>`;
    });
    html+=`</div><div class="sbox">
      <div class="srow"><span class="sl">Ventas</span><span class="sv">S/${d.totales.ventas.toFixed(2)}</span></div>
      <div class="srow"><span class="sl">Premios</span><span class="sv" style="color:var(--red)">S/${d.totales.premios.toFixed(2)}</span></div>
      <div class="srow"><span class="sl">Comisión</span><span class="sv">S/${d.totales.comision.toFixed(2)}</span></div>
      <div class="srow"><span class="sl">Balance</span><span class="sv" style="color:${d.totales.balance>=0?'var(--green)':'var(--red)'}">S/${d.totales.balance.toFixed(2)}</span></div>
    </div>`;
    c.innerHTML=html;
  });
}

// ===== CAJA HOY =====
function openCaja(){
  openMod('mod-caja');
  fetch('/api/caja').then(r=>r.json()).then(d=>{
    if(d.error) return;
    let bc=d.balance>=0?'g':'r';
    document.getElementById('caja-body').innerHTML=`
      <div class="caja-grid">
        <div class="cg"><div class="cgl">VENTAS</div><div class="cgv">S/${d.ventas.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">PREMIOS PAGADOS</div><div class="cgv r">S/${d.premios.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">COMISIÓN</div><div class="cgv">S/${d.comision.toFixed(2)}</div></div>
        <div class="cg"><div class="cgl">BALANCE</div><div class="cgv ${bc}">S/${d.balance.toFixed(2)}</div></div>
      </div>
      <div class="sbox">
        <div class="srow"><span class="sl">Tickets vendidos</span><span class="sv">${d.total_tickets}</span></div>
        <div class="srow"><span class="sl">Con premio pendiente</span><span class="sv" style="color:#c08020">${d.tickets_pendientes}</span></div>
      </div>`;
  });
}

// ===== PAGAR =====
function openPagar(){ openMod('mod-pagar'); document.getElementById('pag-serial').value=''; document.getElementById('pag-res').innerHTML=''; }
function verificarTicket(){
  let s=document.getElementById('pag-serial').value.trim(); if(!s)return;
  let c=document.getElementById('pag-res');
  fetch('/api/verificar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<div style="background:var(--red-bg);color:var(--red);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid var(--red-border)">❌ ${d.error}</div>`;return;}
    let col=d.total_ganado>0?'var(--green)':'var(--text2)';
    c.innerHTML=`<div style="border:1px solid ${col};border-radius:4px;padding:14px;margin-top:10px">
      <div style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:10px">TICKET #${s}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="color:var(--text2);font-size:.8rem">PREMIO</span>
        <span style="color:${col};font-family:'Oswald',sans-serif;font-size:1.2rem;font-weight:700">S/${d.total_ganado.toFixed(2)}</span>
      </div>
      ${d.total_ganado>0?`<button onclick="pagarTicket(${d.ticket_id},${d.total_ganado})" style="width:100%;padding:11px;background:linear-gradient(135deg,#0a3020,#062018);color:var(--green);border:1px solid #0d5a2a;border-radius:3px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.85rem">💰 CONFIRMAR PAGO S/${d.total_ganado.toFixed(2)}</button>`:'<div style="color:var(--text2);text-align:center;font-size:.8rem;padding:6px">SIN PREMIO</div>'}
    </div>`;
  });
}
function pagarTicket(tid,m){
  if(!confirm(`¿Confirmar pago S/${m}?`))return;
  fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){toast('✅ Ticket pagado','ok');closeMod('mod-pagar');}
    else toast(d.error||'Error','err');
  });
}

// ===== ANULAR =====
function openAnular(){ openMod('mod-anular'); document.getElementById('an-serial').value=''; document.getElementById('an-res').innerHTML=''; }
function anularTicket(){
  let s=document.getElementById('an-serial').value.trim(); if(!s)return;
  fetch('/api/anular-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    let c=document.getElementById('an-res');
    if(d.status==='ok') c.innerHTML=`<div style="background:#062012;color:var(--green);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid #0d5a2a">✅ ${d.mensaje}</div>`;
    else c.innerHTML=`<div style="background:var(--red-bg);color:var(--red);padding:10px;border-radius:3px;text-align:center;margin-top:8px;border:1px solid var(--red-border)">❌ ${d.error}</div>`;
  });
}

// ===== MODAL =====
function openMod(id){ document.getElementById(id).classList.add('open'); }
function closeMod(id){ document.getElementById(id).classList.remove('open'); }
document.querySelectorAll('.modal').forEach(m=>{
  m.addEventListener('click',e=>{ if(e.target===m) m.classList.remove('open'); });
});

// ===== TOAST =====
function toast(msg,tipo){
  let t=document.getElementById('toast');
  t.textContent=msg; t.className='toast '+tipo; t.style.display='block';
  clearTimeout(window._tt);
  window._tt=setTimeout(()=>t.style.display='none',2800);
}

document.addEventListener('DOMContentLoaded',init);
</script>
</body></html>'''


ADMIN_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADMIN — ZOOLO</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Rajdhani:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#06090f;--panel:#0a0e18;--card:#0d1220;--border:#1a2540;--gold:#f5a623;--blue:#2060d0;--teal:#00b4d8;--red:#e53e3e;--green:#22c55e;--purple:#a855f7;--text:#c8d8f0;--text2:#4a6090}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh}
.topbar{background:var(--panel);border-bottom:2px solid var(--border);padding:0 16px;height:40px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.brand{font-family:'Oswald',sans-serif;font-size:1rem;font-weight:700;color:#fff;letter-spacing:2px}
.brand em{color:var(--gold);font-style:normal}
.btn-exit{background:#1a0808;color:#e05050;border:1px solid #6b1515;padding:6px 12px;border-radius:3px;cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:600;font-size:.78rem;letter-spacing:1px}
.tabs{display:flex;background:#050810;border-bottom:2px solid var(--border);overflow-x:auto;position:sticky;top:40px;z-index:99}
.tab{padding:11px 16px;cursor:pointer;color:var(--text2);font-size:.75rem;font-family:'Oswald',sans-serif;letter-spacing:2px;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap}
.tab.active{color:var(--teal);border-bottom-color:var(--teal);background:#050e12}
.tc{display:none;padding:14px;max-width:960px;margin:auto}
.tc.active{display:block}
.fbox{background:var(--panel);border:1px solid var(--border);border-radius:4px;padding:16px;margin-bottom:12px}
.fbox h3{font-family:'Oswald',sans-serif;color:var(--teal);margin-bottom:12px;font-size:.85rem;letter-spacing:2px}
.frow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.frow input,.frow select{flex:1;min-width:110px;padding:9px 11px;background:#060e1e;border:1px solid var(--border);border-radius:3px;color:var(--gold);font-family:'Rajdhani',sans-serif;font-size:.85rem}
.frow input:focus,.frow select:focus{outline:none;border-color:var(--teal)}
.btn-s{padding:9px 16px;background:linear-gradient(135deg,#062012,#041a0e);color:var(--green);border:1px solid #0d5a2a;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:2px;cursor:pointer;font-size:.78rem;white-space:nowrap}
.btn-d{padding:9px 16px;background:#1a0808;color:var(--red);border:1px solid #6b1515;border-radius:3px;font-weight:700;font-family:'Oswald',sans-serif;letter-spacing:2px;cursor:pointer;font-size:.78rem}
.btn-sec{padding:7px 12px;background:var(--card);color:var(--text2);border:1px solid var(--border);border-radius:3px;cursor:pointer;font-size:.78rem;font-family:'Rajdhani',sans-serif;letter-spacing:1px}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.sc{background:var(--card);border:1px solid var(--border);border-radius:3px;padding:14px;text-align:center}
.sc h3{color:var(--text2);font-size:.68rem;letter-spacing:2px;font-family:'Oswald',sans-serif;margin-bottom:6px}
.sc p{color:var(--gold);font-size:1.3rem;font-weight:700;font-family:'Oswald',sans-serif}
.sc p.g{color:var(--green)}.sc p.r{color:var(--red)}
.ri{display:flex;justify-content:space-between;align-items:center;padding:9px 11px;margin:4px 0;background:var(--card);border-radius:3px;border-left:2px solid var(--border)}
.ri.ok{border-left-color:var(--green)}
.msg{padding:9px 12px;border-radius:3px;margin:6px 0;font-size:.82rem;font-family:'Oswald',sans-serif;letter-spacing:1px;text-align:center}
.msg.ok{background:#062012;color:var(--green);border:1px solid #0d5a2a}
.msg.err{background:#1a0808;color:var(--red);border:1px solid #6b1515}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{background:var(--card);color:var(--teal);padding:9px;text-align:left;border-bottom:1px solid var(--border);font-family:'Oswald',sans-serif;letter-spacing:1px;font-size:.72rem}
td{padding:7px 9px;border-bottom:1px solid #0a0e18;color:var(--text)}
tr:hover td{background:var(--card)}
.rank-item{display:flex;justify-content:space-between;align-items:center;padding:11px 13px;margin:5px 0;background:var(--card);border-radius:3px;border-left:2px solid var(--gold)}
.glmsg{position:fixed;top:48px;left:50%;transform:translateX(-50%);z-index:999;min-width:240px;display:none}
.sbox{background:var(--card);border-radius:3px;padding:10px;margin:6px 0;border:1px solid var(--border)}
.srow{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #0a0e18;font-size:.8rem}
.srow:last-child{border-bottom:none}
.sl{color:var(--text2)}.sv{color:var(--gold);font-weight:700;font-family:'Oswald',sans-serif}
.btn-edit{padding:4px 10px;background:#0d2a60;color:#7ab0ff;border:1px solid #1a3a80;border-radius:3px;cursor:pointer;font-size:.72rem;font-family:'Rajdhani',sans-serif;letter-spacing:1px}
::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:#050810}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style></head><body>
<div class="topbar">
  <div class="brand">ZOO<em>LO</em> — ADMIN</div>
  <button class="btn-exit" onclick="location.href='/logout'">SALIR</button>
</div>
<div id="glmsg" class="glmsg"></div>
<div class="tabs">
  <div class="tab active" onclick="showTab('dashboard')">📊 DASHBOARD</div>
  <div class="tab" onclick="showTab('resultados')">🎯 RESULTADOS</div>
  <div class="tab" onclick="showTab('tripletas')">🔮 TRIPLETAS</div>
  <div class="tab" onclick="showTab('riesgo')">⚠️ RIESGO</div>
  <div class="tab" onclick="showTab('reportes')">📈 REPORTES</div>
  <div class="tab" onclick="showTab('agencias')">🏪 AGENCIAS</div>
  <div class="tab" onclick="showTab('operaciones')">💰 OPERACIONES</div>
</div>

<div id="tc-dashboard" class="tc active">
  <div class="sgrid">
    <div class="sc"><h3>VENTAS HOY</h3><p id="d-v">--</p></div>
    <div class="sc"><h3>PREMIOS PAGADOS</h3><p id="d-p" class="r">--</p></div>
    <div class="sc"><h3>COMISIONES</h3><p id="d-c">--</p></div>
    <div class="sc"><h3>BALANCE</h3><p id="d-b">--</p></div>
  </div>
  <div class="fbox"><h3>🏪 POR AGENCIA (HOY)</h3><div id="dash-ags"></div></div>
</div>

<div id="tc-resultados" class="tc">
  <div class="fbox">
    <h3>📅 FECHA</h3>
    <div class="frow"><input type="date" id="ra-fecha"><button class="btn-s" onclick="cargarRA()">VER</button></div>
  </div>
  <div class="fbox">
    <h3>📋 RESULTADOS</h3>
    <div id="ra-lista" style="max-height:400px;overflow-y:auto"></div>
  </div>
  <div class="fbox">
    <h3>✏️ CARGAR RESULTADO</h3>
    <div class="frow">
      <select id="ra-hora">{% for h in horarios %}<option value="{{h}}">{{h}}</option>{% endfor %}</select>
      <select id="ra-animal">{% for k,v in animales.items() %}<option value="{{k}}">{{k}} — {{v}}</option>{% endfor %}</select>
      <input type="date" id="ra-fi" style="max-width:160px">
      <button class="btn-s" onclick="guardarRA()">💾 GUARDAR</button>
    </div>
    <div id="ra-msg"></div>
  </div>
</div>

<div id="tc-tripletas" class="tc">
  <div class="fbox">
    <h3>🔮 TRIPLETAS HOY</h3>
    <button class="btn-s" onclick="cargarTrip()" style="margin-bottom:10px">🔄 ACTUALIZAR</button>
    <div id="tri-stats" style="margin-bottom:10px"></div>
    <div id="tri-lista" style="max-height:500px;overflow-y:auto"></div>
  </div>
</div>

<div id="tc-riesgo" class="tc">
  <div class="fbox">
    <h3>⚠️ RIESGO</h3>
    <button class="btn-s" onclick="cargarRiesgo()" style="margin-bottom:10px">🔄 ACTUALIZAR</button>
    <div id="riesgo-info" style="color:var(--gold);font-family:'Oswald',sans-serif;font-size:.82rem;letter-spacing:1px;margin-bottom:8px"></div>
    <div id="riesgo-lista" style="max-height:500px;overflow-y:auto"></div>
  </div>
</div>

<div id="tc-reportes" class="tc">
  <div class="fbox">
    <h3>📈 REPORTE POR RANGO</h3>
    <div class="frow">
      <input type="date" id="rep-ini"><input type="date" id="rep-fin">
      <button class="btn-s" onclick="generarReporte()">GENERAR</button>
      <button class="btn-sec" onclick="exportarCSV()">📥 CSV</button>
    </div>
    <div id="rep-out" style="display:none">
      <div class="sgrid" style="margin-top:12px">
        <div class="sc"><h3>VENTAS</h3><p id="rv">--</p></div>
        <div class="sc"><h3>PREMIOS</h3><p id="rp" class="r">--</p></div>
        <div class="sc"><h3>COMISIÓN</h3><p id="rc">--</p></div>
        <div class="sc"><h3>BALANCE</h3><p id="rb">--</p></div>
      </div>
      <div style="overflow-x:auto;margin-top:10px"><table>
        <thead><tr><th>Fecha</th><th>Tickets</th><th>Ventas</th><th>Premios</th><th>Comisión</th><th>Balance</th></tr></thead>
        <tbody id="rep-tbody"></tbody>
      </table></div>
      <h4 style="color:var(--gold);margin:14px 0 8px;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.8rem">POR AGENCIA</h4>
      <div id="rep-ags"></div>
    </div>
  </div>
</div>

<div id="tc-agencias" class="tc">
  <div class="fbox">
    <h3>➕ NUEVA AGENCIA</h3>
    <div class="frow">
      <input type="text" id="ag-u" placeholder="Usuario">
      <input type="password" id="ag-p" placeholder="Contraseña">
      <input type="text" id="ag-n" placeholder="Nombre agencia">
      <button class="btn-s" onclick="crearAg()">CREAR</button>
    </div>
    <div id="ag-msg"></div>
  </div>
  <div class="fbox">
    <h3>🏪 AGENCIAS</h3>
    <button class="btn-sec" onclick="cargarAgs()" style="margin-bottom:8px">🔄 Actualizar</button>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>ID</th><th>Usuario</th><th>Nombre</th><th>Comisión</th><th>Estado</th><th>Acción</th></tr></thead>
      <tbody id="tabla-ags"></tbody>
    </table></div>
  </div>
</div>

<div id="tc-operaciones" class="tc">
  <div class="fbox">
    <h3>💰 VERIFICAR / PAGAR</h3>
    <div class="frow"><input type="text" id="op-ser" placeholder="Serial"><button class="btn-s" onclick="verificarAdm()">VERIFICAR</button></div>
    <div id="op-res"></div>
  </div>
  <div class="fbox">
    <h3>❌ ANULAR (ADMIN)</h3>
    <div class="frow"><input type="text" id="an-ser" placeholder="Serial"><button class="btn-d" onclick="anularAdm()">ANULAR</button></div>
    <div id="an-res"></div>
  </div>
</div>

<script>
const ANIMALES = {{ animales | tojson }};
const HORARIOS = {{ horarios | tojson }};
const TABS=['dashboard','resultados','tripletas','riesgo','reportes','agencias','operaciones'];

function showTab(id){
  TABS.forEach(t=>{
    document.getElementById('tc-'+t).classList.toggle('active',t===id);
    document.querySelectorAll('.tab')[TABS.indexOf(t)].classList.toggle('active',t===id);
  });
  if(id==='dashboard') cargarDash();
  if(id==='resultados'){setHoy('ra-fecha');setHoy('ra-fi');cargarRA();}
  if(id==='tripletas') cargarTrip();
  if(id==='riesgo') cargarRiesgo();
  if(id==='agencias') cargarAgs();
}
function setHoy(id){let e=document.getElementById(id);if(e)e.value=new Date().toISOString().split('T')[0];}
function showMsg(id,msg,t){let e=document.getElementById(id);e.innerHTML=`<div class="msg ${t}">${msg}</div>`;setTimeout(()=>e.innerHTML='',4000);}
function glMsg(msg,t){let e=document.getElementById('glmsg');e.innerHTML=`<div class="msg ${t}" style="box-shadow:0 4px 20px rgba(0,0,0,.8)">${msg}</div>`;e.style.display='block';setTimeout(()=>e.style.display='none',4000);}

function cargarDash(){
  fetch('/admin/reporte-agencias').then(r=>r.json()).then(d=>{
    if(d.error)return;
    document.getElementById('d-v').textContent='S/'+d.global.ventas.toFixed(2);
    document.getElementById('d-p').textContent='S/'+d.global.pagos.toFixed(2);
    document.getElementById('d-c').textContent='S/'+d.global.comisiones.toFixed(2);
    let bp=document.getElementById('d-b'); bp.textContent='S/'+d.global.balance.toFixed(2);
    bp.className=d.global.balance>=0?'g':'r';
    let html=d.agencias.length?'':'<p style="color:var(--text2);text-align:center;padding:20px;font-size:.78rem;letter-spacing:2px">SIN ACTIVIDAD HOY</p>';
    d.agencias.forEach(ag=>{
      html+=`<div class="rank-item">
        <div><b style="color:var(--gold);font-family:'Oswald',sans-serif">${ag.nombre}</b>
          <span style="color:var(--text2);font-size:.72rem;margin-left:6px">${ag.usuario} — ${ag.tickets} tickets</span></div>
        <div style="text-align:right">
          <div style="color:var(--green);font-family:'Oswald',sans-serif">S/${ag.ventas.toFixed(2)}</div>
          <div style="color:${ag.balance>=0?'var(--green)':'var(--red)'};font-size:.82rem">Bal: S/${ag.balance.toFixed(2)}</div>
        </div>
      </div>`;
    });
    document.getElementById('dash-ags').innerHTML=html;
  });
}

function cargarRA(){
  let f=document.getElementById('ra-fecha').value; if(!f)return;
  let c=document.getElementById('ra-lista');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:12px;font-size:.75rem;letter-spacing:2px">CARGANDO...</p>';
  fetch('/api/resultados-fecha-admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha:f})})
  .then(r=>r.json()).then(d=>{
    let html='';
    HORARIOS.forEach(h=>{
      let res=d.resultados[h];
      html+=`<div class="ri ${res?'ok':''}">
        <span style="color:var(--gold);font-weight:700;font-family:'Oswald',sans-serif;font-size:.82rem">${h}</span>
        <div style="display:flex;align-items:center;gap:8px">
          ${res?`<span style="color:var(--green);font-weight:600">${res.animal} — ${res.nombre}</span>`:'<span style="color:#1e2a40;font-size:.78rem">PENDIENTE</span>'}
          <button class="btn-edit" onclick="preRA('${h}','${f}',${res?`'${res.animal}'`:'null'})">${res?'✏️ Editar':'➕'}</button>
        </div>
      </div>`;
    });
    c.innerHTML=html;
  });
}
function preRA(h,f,a){
  document.getElementById('ra-hora').value=h;
  document.getElementById('ra-fi').value=f;
  if(a&&a!=='null') document.getElementById('ra-animal').value=a;
}
function guardarRA(){
  let hora=document.getElementById('ra-hora').value;
  let animal=document.getElementById('ra-animal').value;
  let fecha=document.getElementById('ra-fi').value;
  let form=new FormData(); form.append('hora',hora);form.append('animal',animal);if(fecha)form.append('fecha',fecha);
  fetch('/admin/guardar-resultado',{method:'POST',body:form}).then(r=>r.json()).then(d=>{
    if(d.status==='ok'){showMsg('ra-msg','✅ '+d.mensaje,'ok');cargarRA();}
    else showMsg('ra-msg','❌ '+d.error,'err');
  });
}

function cargarTrip(){
  let l=document.getElementById('tri-lista');
  l.innerHTML='<p style="color:var(--text2);text-align:center;padding:12px;font-size:.75rem">CARGANDO...</p>';
  fetch('/admin/tripletas-hoy').then(r=>r.json()).then(d=>{
    document.getElementById('tri-stats').innerHTML=`
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <div class="sc" style="flex:1"><h3>TOTAL</h3><p>${d.total}</p></div>
        <div class="sc" style="flex:1"><h3>GANADORAS</h3><p class="g">${d.ganadoras}</p></div>
        <div class="sc" style="flex:1"><h3>PREMIOS</h3><p class="r">S/${d.total_premios.toFixed(2)}</p></div>
      </div>`;
    if(!d.tripletas.length){l.innerHTML='<p style="color:var(--text2);text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">NO HAY TRIPLETAS HOY</p>';return;}
    let html='';
    d.tripletas.forEach(tr=>{
      html+=`<div style="padding:9px 11px;margin:4px 0;background:var(--card);border-left:2px solid var(--purple);border-radius:3px;font-size:.8rem ${tr.gano?';background:rgba(34,197,94,.05);border-left-color:var(--green)':''}">
        <div style="display:flex;justify-content:space-between">
          <b style="color:#c084fc;font-family:'Oswald',sans-serif">${tr.nombres[0]} • ${tr.nombres[1]} • ${tr.nombres[2]}</b>
          <span style="color:var(--text2);font-size:.72rem">${tr.agencia} | S/${tr.monto}x60</span>
        </div>
        <div style="color:${tr.gano?'var(--green)':'var(--text2)'};font-size:.76rem;margin-top:3px">
          ${tr.salieron.length?'Salieron: '+tr.salieron.join(', ')+' ('+tr.salieron.length+'/3)':'Pendiente'}
          ${tr.gano?` — <b>+S/${tr.premio.toFixed(2)}</b>`:''}
        </div>
      </div>`;
    });
    l.innerHTML=html;
  });
}

function cargarRiesgo(){
  fetch('/admin/riesgo').then(r=>r.json()).then(d=>{
    document.getElementById('riesgo-info').textContent=`SORTEO: ${d.sorteo_objetivo||'N/A'} | TOTAL: S/${(d.total_apostado||0).toFixed(2)}`;
    let l=document.getElementById('riesgo-lista');
    if(!Object.keys(d.riesgo).length){l.innerHTML='<p style="color:var(--text2);text-align:center;padding:20px;font-size:.75rem;letter-spacing:2px">SIN APUESTAS</p>';return;}
    let html='';
    for(let[k,v] of Object.entries(d.riesgo)){
      html+=`<div style="padding:9px 11px;margin:4px 0;background:var(--card);border-left:2px solid ${v.es_lechuza?'var(--gold)':'var(--blue)'};border-radius:3px;font-size:.8rem">
        <div style="display:flex;justify-content:space-between">
          <b style="color:${v.es_lechuza?'var(--gold)':'var(--text)'}">${k}${v.es_lechuza?' ⚠️':''}</b>
          <span style="color:var(--text2)">${v.porcentaje}%</span>
        </div>
        <div style="color:var(--text2);font-size:.75rem;margin-top:2px">Apostado: S/${v.apostado.toFixed(2)} | Pagaría: <span style="color:var(--red)">S/${v.pagaria.toFixed(2)}</span></div>
      </div>`;
    }
    l.innerHTML=html;
  });
}

function generarReporte(){
  let ini=document.getElementById('rep-ini').value; let fin=document.getElementById('rep-fin').value;
  if(!ini||!fin){glMsg('Seleccione fechas','err');return;}
  glMsg('Generando...','ok');
  Promise.all([
    fetch('/admin/estadisticas-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json()),
    fetch('/admin/reporte-agencias-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json())
  ]).then(([est,ag])=>{
    document.getElementById('rep-out').style.display='block';
    document.getElementById('rv').textContent='S/'+est.totales.ventas.toFixed(2);
    document.getElementById('rp').textContent='S/'+est.totales.premios.toFixed(2);
    document.getElementById('rc').textContent='S/'+est.totales.comisiones.toFixed(2);
    let rb=document.getElementById('rb'); rb.textContent='S/'+est.totales.balance.toFixed(2); rb.className=est.totales.balance>=0?'g':'r';
    let tb=document.getElementById('rep-tbody'); tb.innerHTML='';
    est.resumen_por_dia.forEach(d=>{
      let col=d.balance>=0?'var(--green)':'var(--red)';
      tb.innerHTML+=`<tr><td>${d.fecha}</td><td>${d.tickets}</td><td>S/${d.ventas.toFixed(2)}</td><td>S/${d.premios.toFixed(2)}</td><td>S/${d.comisiones.toFixed(2)}</td><td style="color:${col};font-weight:700;font-family:'Oswald',sans-serif">S/${d.balance.toFixed(2)}</td></tr>`;
    });
    let agHtml='';
    if(ag.agencias) ag.agencias.forEach(a=>{
      agHtml+=`<div class="rank-item">
        <div><b style="color:var(--gold);font-family:'Oswald',sans-serif">${a.nombre}</b>
          <span style="color:var(--text2);font-size:.72rem;margin-left:6px">${a.usuario} | ${a.tickets}t | ${a.porcentaje_ventas||0}%</span></div>
        <div style="text-align:right">
          <div style="color:var(--text);font-size:.85rem">S/${a.ventas.toFixed(2)}</div>
          <div style="color:${a.balance>=0?'var(--green)':'var(--red)'};font-family:'Oswald',sans-serif">S/${a.balance.toFixed(2)}</div>
        </div>
      </div>`;
    });
    document.getElementById('rep-ags').innerHTML=agHtml;
    glMsg('Reporte generado','ok');
  }).catch(()=>glMsg('Error','err'));
}

function exportarCSV(){
  let ini=document.getElementById('rep-ini').value; let fin=document.getElementById('rep-fin').value;
  if(!ini||!fin){glMsg('Seleccione fechas','err');return;}
  fetch('/admin/exportar-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})})
  .then(r=>r.blob()).then(b=>{let a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=`zoolo_${ini}_${fin}.csv`;a.click();});
}

function cargarAgs(){
  fetch('/admin/lista-agencias').then(r=>r.json()).then(d=>{
    let t=document.getElementById('tabla-ags'); t.innerHTML='';
    if(!d.length){t.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--text2);padding:16px">SIN AGENCIAS</td></tr>';return;}
    d.forEach(a=>{
      t.innerHTML+=`<tr><td>${a.id}</td><td>${a.usuario}</td><td>${a.nombre_agencia}</td>
        <td>${(a.comision*100).toFixed(0)}%</td>
        <td><span style="color:${a.activa?'var(--green)':'var(--red)'}">● ${a.activa?'ACTIVA':'INACTIVA'}</span></td>
        <td><button class="btn-sec" onclick="toggleAg(${a.id},${a.activa})">${a.activa?'Desactivar':'Activar'}</button></td></tr>`;
    });
  });
}
function crearAg(){
  let u=document.getElementById('ag-u').value.trim(); let p=document.getElementById('ag-p').value.trim(); let n=document.getElementById('ag-n').value.trim();
  if(!u||!p||!n){showMsg('ag-msg','Complete todos los campos','err');return;}
  let form=new FormData(); form.append('usuario',u);form.append('password',p);form.append('nombre',n);
  fetch('/admin/crear-agencia',{method:'POST',body:form}).then(r=>r.json()).then(d=>{
    if(d.status==='ok'){showMsg('ag-msg','✅ '+d.mensaje,'ok');document.getElementById('ag-u').value='';document.getElementById('ag-p').value='';document.getElementById('ag-n').value='';cargarAgs();}
    else showMsg('ag-msg','❌ '+d.error,'err');
  });
}
function toggleAg(id,a){
  fetch('/admin/editar-agencia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,activa:!a})})
  .then(r=>r.json()).then(d=>{if(d.status==='ok')cargarAgs();else glMsg(d.error,'err');});
}

function verificarAdm(){
  let s=document.getElementById('op-ser').value.trim(); if(!s)return;
  let c=document.getElementById('op-res');
  c.innerHTML='<p style="color:var(--text2);text-align:center;padding:8px;font-size:.75rem;letter-spacing:2px">VERIFICANDO...</p>';
  fetch('/api/verificar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    if(d.error){c.innerHTML=`<div class="msg err">${d.error}</div>`;return;}
    let col=d.total_ganado>0?'var(--green)':'#1e2a40';
    c.innerHTML=`<div style="border:1px solid ${col};border-radius:4px;padding:14px;margin-top:8px">
      <div style="color:var(--teal);font-family:'Oswald',sans-serif;letter-spacing:2px;margin-bottom:10px">TICKET #${s}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="color:var(--text2);font-size:.8rem">PREMIO</span>
        <span style="color:${col};font-family:'Oswald',sans-serif;font-size:1.1rem">S/${d.total_ganado.toFixed(2)}</span>
      </div>
      ${d.total_ganado>0?`<button onclick="pagarAdm(${d.ticket_id},${d.total_ganado})" style="width:100%;padding:10px;background:linear-gradient(135deg,#062012,#041a0e);color:var(--green);border:1px solid #0d5a2a;border-radius:3px;font-weight:700;cursor:pointer;font-family:'Oswald',sans-serif;letter-spacing:2px;font-size:.82rem">💰 CONFIRMAR PAGO S/${d.total_ganado.toFixed(2)}</button>`:'<div class="msg err">SIN PREMIO</div>'}
    </div>`;
  });
}
function pagarAdm(tid,m){
  if(!confirm(`¿Confirmar pago S/${m}?`))return;
  fetch('/api/pagar-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_id:tid})})
  .then(r=>r.json()).then(d=>{
    if(d.status==='ok'){glMsg('✅ Ticket pagado','ok');document.getElementById('op-res').innerHTML='';}
    else glMsg('❌ '+d.error,'err');
  });
}
function anularAdm(){
  let s=document.getElementById('an-ser').value.trim(); if(!s)return;
  if(!confirm('¿Anular ticket '+s+'?'))return;
  fetch('/api/anular-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:s})})
  .then(r=>r.json()).then(d=>{
    let c=document.getElementById('an-res');
    if(d.status==='ok') c.innerHTML='<div class="msg ok">✅ '+d.mensaje+'</div>';
    else c.innerHTML='<div class="msg err">❌ '+d.error+'</div>';
  });
}

document.addEventListener('DOMContentLoaded',()=>{
  let hoy=new Date().toISOString().split('T')[0];
  ['rep-ini','rep-fin','ra-fecha','ra-fi'].forEach(id=>{let e=document.getElementById(id);if(e)e.value=hoy;});
  cargarDash();
});

// Falta en admin el endpoint de estadisticas-rango
{% raw %}
{% endraw %}
</script>
<script>
// Necesario para reportes admin
async function fetchEstadisticasRango(ini,fin){
  return fetch('/admin/estadisticas-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json());
}
async function fetchReporteAgenciasRango(ini,fin){
  return fetch('/admin/reporte-agencias-rango',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fecha_inicio:ini,fecha_fin:fin})}).then(r=>r.json());
}
</script>
</body></html>'''

@app.route('/admin/estadisticas-rango', methods=['POST'])
@admin_required
def estadisticas_rango():
    try:
        data=request.get_json(); fi=data.get('fecha_inicio'); ff=data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        dti=datetime.strptime(fi,"%Y-%m-%d"); dtf=datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        with get_db() as db:
            all_t=db.execute("SELECT * FROM tickets WHERE anulado=0 ORDER BY id DESC LIMIT 10000").fetchall()
        dias={}; total_v=total_p=total_t=0
        for t in all_t:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            dk=dt.strftime("%d/%m/%Y")
            if dk not in dias: dias[dk]={'ventas':0,'tickets':0,'ids':[]}
            dias[dk]['ventas']+=t['total']; dias[dk]['tickets']+=1; dias[dk]['ids'].append(t['id'])
            total_v+=t['total']; total_t+=1
        resumen=[]; total_p=0
        for dk in sorted(dias.keys()):
            d=dias[dk]; prem=0
            for tid in d['ids']:
                with get_db() as db2: prem+=calcular_premio_ticket(tid,db2)
            total_p+=prem
            cd=d['ventas']*COMISION_AGENCIA
            resumen.append({'fecha':dk,'ventas':round(d['ventas'],2),'premios':round(prem,2),
                'comisiones':round(cd,2),'balance':round(d['ventas']-prem-cd,2),'tickets':d['tickets']})
        tc=total_v*COMISION_AGENCIA
        return jsonify({'resumen_por_dia':resumen,
            'totales':{'ventas':round(total_v,2),'premios':round(total_p,2),
                'comisiones':round(tc,2),'balance':round(total_v-total_p-tc,2),'tickets':total_t}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/admin/reporte-agencias-rango', methods=['POST'])
@admin_required
def reporte_agencias_rango():
    try:
        data=request.get_json(); fi=data.get('fecha_inicio'); ff=data.get('fecha_fin')
        if not fi or not ff: return jsonify({'error':'Fechas requeridas'}),400
        dti=datetime.strptime(fi,"%Y-%m-%d"); dtf=datetime.strptime(ff,"%Y-%m-%d").replace(hour=23,minute=59)
        with get_db() as db:
            ags=db.execute("SELECT * FROM agencias WHERE es_admin=0").fetchall()
            all_t=db.execute("SELECT * FROM tickets WHERE anulado=0 ORDER BY id DESC LIMIT 50000").fetchall()
        stats={ag['id']:{'nombre':ag['nombre_agencia'],'usuario':ag['usuario'],'tickets':0,'ventas':0,'premios_teoricos':0,'comision_pct':ag['comision']} for ag in ags}
        for t in all_t:
            dt=parse_fecha(t['fecha'])
            if not dt or dt<dti or dt>dtf: continue
            aid=t['agencia_id']
            if aid not in stats: continue
            stats[aid]['tickets']+=1; stats[aid]['ventas']+=t['total']
            with get_db() as db2: p=calcular_premio_ticket(t['id'],db2)
            stats[aid]['premios_teoricos']+=p
        out=[]
        for s in stats.values():
            if s['tickets']==0: continue
            com=s['ventas']*s['comision_pct']
            s['comision']=round(com,2); s['balance']=round(s['ventas']-s['premios_teoricos']-com,2)
            s['ventas']=round(s['ventas'],2); s['premios_teoricos']=round(s['premios_teoricos'],2)
            out.append(s)
        out.sort(key=lambda x:x['ventas'],reverse=True)
        tv=sum(x['ventas'] for x in out)
        if tv>0:
            for x in out: x['porcentaje_ventas']=round(x['ventas']/tv*100,1)
        total={'tickets':sum(x['tickets'] for x in out),'ventas':round(tv,2),
            'premios':round(sum(x['premios_teoricos'] for x in out),2),
            'comision':round(sum(x['comision'] for x in out),2),
            'balance':round(sum(x['balance'] for x in out),2)}
        return jsonify({'agencias':out,'total':total,'periodo':{'inicio':fi,'fin':ff}})
    except Exception as e:
        return jsonify({'error':str(e)}),500

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print("="*55)
    print("  🦁 ZOOLO CASINO v2.1 — Layout Compacto")
    print("="*55)
    print(f"  URL: http://localhost:{port}")
    print(f"  Admin: usuario=admin  password=admin123")
    print("="*55)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

