from aiohttp import web
import aiohttp_jinja2
import jinja2
import sqlite3
import asyncio
import os
import json

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'todo.db')

async def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            frequency TEXT,
            assigned_to TEXT,
            points INTEGER,
            completed BOOLEAN
        )
    ''')
    conn.commit()
    return conn

async def get_tasks_from_db(db):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "frequency": row[3],
            "assigned_to": row[4],
            "points": row[5],
            "completed": bool(row[6])
        })
    return tasks

async def get_scores_from_db(db):
    cursor = db.cursor()
    cursor.execute("SELECT SUM(points) FROM tasks WHERE completed = 1 AND assigned_to LIKE '%A%'")
    score_a = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(points) FROM tasks WHERE completed = 1 AND assigned_to LIKE '%B%'")
    score_b = cursor.fetchone()[0] or 0
    return {"difference": score_a - score_b}

async def create_task_in_db(db, task_data):
    conn = db
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (name, description, frequency, assigned_to, points, completed) VALUES (?, ?, ?, ?, ?, ?)",
        (task_data['name'], task_data['description'], task_data['frequency'], task_data['assigned_to'], task_data['points'], False)
    )
    conn.commit()
    task_data['id'] = cursor.lastrowid #Recupera l'ID
    task_data['completed'] = False #Imposta completato a false
    return task_data

async def update_task_in_db(db, task_id, task_data):
    conn = db
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET name=?, description=?, frequency=?, assigned_to=?, points=? WHERE id=?",
        (task_data['name'], task_data['description'], task_data['frequency'], task_data['assigned_to'], task_data['points'], task_id)
    )
    conn.commit()
    return task_data

async def delete_task_in_db(db, task_id):
     conn = db
     cursor = conn.cursor()
     cursor.execute("DELETE FROM tasks WHERE id=?", (task_id,))
     conn.commit()

async def complete_task_in_db(db, task_id, completed_by):
    conn = db
    cursor = conn.cursor()

    # Ottieni l'assegnazione corrente del task
    cursor.execute("SELECT assigned_to, points FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        return None, web.HTTPNotFound(text="Task non trovato") #Restituisci un errore 404
    original_assigned_to, points = row

    # Aggiorna lo stato del task
    cursor.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))


    conn.commit()
    return {"id": task_id, "completed": True, "points": points}, None #Restituisci i dati

async def handle_index(request):
    context = {
        "tasks": await get_tasks_from_db(request.app['db']),
        "scores": await get_scores_from_db(request.app['db'])
    }
    response = aiohttp_jinja2.render_template('index.html', request, context)
    return response

async def handle_create_task_page(request):
    response = aiohttp_jinja2.render_template('create_task.html', request, {})
    return response

async def handle_get_tasks(request):
    tasks = await get_tasks_from_db(request.app['db'])
    return web.json_response(tasks)

async def handle_create_task(request):
    try:
        data = await request.json()
        #Validazione
        if not all(k in data for k in ("name", "frequency", "assigned_to", "points")):
           return web.HTTPBadRequest(text="Dati mancanti")
        if not data['name'] or not data['frequency'] or not data['assigned_to']:
            return web.HTTPBadRequest(text="Campi obbligatori mancanti")
        try:
            data['points'] = int(data['points'])
        except ValueError:
            return web.HTTPBadRequest(text="Il punteggio deve essere un numero intero")

        task = await create_task_in_db(request.app['db'], data)
        return web.json_response(task, status=201)  # 201 Created
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Formato JSON non valido")

async def handle_get_task(request):
    task_id = int(request.match_info['id'])
    tasks = await get_tasks_from_db(request.app['db']) # inefficiente, ma per semplicità
    task = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        return web.json_response(task)
    else:
        return web.HTTPNotFound()

async def handle_update_task(request):
    task_id = int(request.match_info['id'])
    try:
        data = await request.json()

        if not all(k in data for k in ("name", "frequency", "assigned_to", "points")):
           return web.HTTPBadRequest(text="Dati mancanti")
        if not data['name'] or not data['frequency'] or not data['assigned_to']:
            return web.HTTPBadRequest(text="Campi obbligatori mancanti")
        try:
            data['points'] = int(data['points'])
        except ValueError:
            return web.HTTPBadRequest(text="Il punteggio deve essere un numero intero")


        updated_task = await update_task_in_db(request.app['db'], task_id, data)
        if updated_task:
            return web.json_response(updated_task)
        else: return web.HTTPNotFound()
    except json.JSONDecodeError:
      return web.HTTPBadRequest(text="Formato JSON non valido")

async def handle_delete_task(request):
    task_id = int(request.match_info['id'])
    await delete_task_in_db(request.app['db'], task_id)
    return web.Response(status=204)  # 204 No Content

async def handle_complete_task(request):
    task_id = int(request.match_info['id'])
    try:
        data = await request.json()  # Assicurati che il corpo della richiesta sia JSON
        completed_by = data.get('completedBy')

        if not completed_by:
            return web.HTTPBadRequest(text="completedBy mancante")  # 400 Bad Request

        task, error = await complete_task_in_db(request.app['db'], task_id, completed_by)
        if error:
           return error #Restituisci l'eventuale errore (es 404)
        
        if not task:
            return web.HTTPNotFound()
        return web.json_response(task)

    except json.JSONDecodeError:
      return web.HTTPBadRequest(text="Formato JSON non valido")

async def handle_get_scores(request):
    scores = await get_scores_from_db(request.app['db'])
    return web.json_response(scores)

async def setup_routes(app):
    app.add_routes([
        web.get('/', handle_index),
        web.get('/create_task', handle_create_task_page),
        web.static('/static', 'www'),
        web.get('/api/tasks', handle_get_tasks),
        web.post('/api/tasks', handle_create_task),
        web.get('/api/tasks/{id}', handle_get_task),
        web.put('/api/tasks/{id}', handle_update_task),
        web.delete('/api/tasks/{id}', handle_delete_task),
        web.post('/api/tasks/{id}/complete', handle_complete_task),
        web.get('/api/scores', handle_get_scores),
    ])

async def on_startup(app):
    app['db'] = await init_db()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(str(app.router['static']._directory)))

if __name__ == "__main__":
    app = web.Application()
    app.on_startup.append(on_startup)
    asyncio.run(setup_routes(app))
    web.run_app(app, host='0.0.0.0', port=8099)