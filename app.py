import time
import random
import csv
import threading
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# --- КОНФИГУРАЦИЯ ---
GRID_SIZE = 20
FIRE_SPREAD_CHANCE = 0.05   # Шанс распространения (было 0.1, стало меньше)
FIRE_SPREAD_THRESHOLD = 40  # Огонь распространяется только если интенсивность > 40
EXTINGUISH_POWER = 20       # Мощность тушения за один "тик"
SENSOR_LOG_FILE = 'sensor_logs.csv'
EVENT_LOG_FILE = 'fire_events.csv'

# --- ИНИЦИАЛИЗАЦИЯ ДАННЫХ ---
fire_grid = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
firefighters = []

# Конфигурация отрядов
squads_info = [
    {'name': 'Альфа', 'color': '#89b4fa', 'start_x': 0, 'start_y': 0, 'count': 5, 'id_start': 1},
    {'name': 'Браво', 'color': '#a6e3a1', 'start_x': GRID_SIZE-1, 'start_y': GRID_SIZE-1, 'count': 5, 'id_start': 6}
]

# Генерация бойцов
for squad in squads_info:
    for i in range(squad['count']):
        firefighters.append({
            'id': squad['id_start'] + i,
            'squad': squad['name'],
            'color': squad['color'],
            'x': squad['start_x'],
            'y': squad['start_y'],
            'temp': 36.6,
            'pulse': random.randint(60, 80),
            'action': 'wait',
            'status': 'OK'
        })

# Подготовка файлов логов
def init_logs():
    with open(SENSOR_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Squad', 'ID', 'Temp', 'Pulse', 'Status', 'X', 'Y'])
    
    with open(EVENT_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Squad', 'ID', 'X', 'Y', 'Extinguished_Amount'])

init_logs()

# --- ЛОГИКА ЭМУЛЯЦИИ ---
def get_neighbors(x, y):
    neighbors = []
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0: continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                neighbors.append((nx, ny))
    return neighbors

def simulation_tick():
    global fire_grid, firefighters
    while True:
        timestamp = time.strftime("%H:%M:%S")

        # 1. Логика огня (стала медленнее)
        new_grid = [row[:] for row in fire_grid]
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                if fire_grid[y][x] > 0:
                    # Огонь разгорается сам по себе, но медленно
                    if fire_grid[y][x] < 100:
                        new_grid[y][x] = min(100, fire_grid[y][x] + 2)
                    
                    # Распространение только если огонь сильный (> Threshold)
                    if fire_grid[y][x] > FIRE_SPREAD_THRESHOLD:
                        for nx, ny in get_neighbors(x, y):
                            # Если клетка пустая и выпал шанс
                            if fire_grid[ny][nx] == 0 and random.random() < FIRE_SPREAD_CHANCE:
                                new_grid[ny][nx] = 10 # Начальное возгорание
        fire_grid = new_grid

        # 2. Логика пожарных
        events_buffer = [] # Буфер для записи событий тушения
        sensors_buffer = [] # Буфер для датчиков

        for ff in firefighters:
            # Поиск ближайшего огня
            nearest_fire = None
            min_dist = 999
            
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    if fire_grid[y][x] > 0:
                        dist = ((ff['x']-x)**2 + (ff['y']-y)**2)**0.5
                        if dist < min_dist:
                            min_dist = dist
                            nearest_fire = (x, y)
            
            # Действия
            if nearest_fire:
                fx, fy = nearest_fire
                if min_dist <= 1.5:
                    # ТУШЕНИЕ
                    ff['action'] = 'extinguishing'
                    old_fire_val = fire_grid[fy][fx]
                    # Тушим огонь
                    fire_grid[fy][fx] = max(0, fire_grid[fy][fx] - EXTINGUISH_POWER)
                    
                    # Записываем событие (сколько потушили)
                    diff = old_fire_val - fire_grid[fy][fx]
                    if diff > 0:
                        events_buffer.append([timestamp, ff['squad'], ff['id'], fx, fy, round(diff, 1)])

                    # Нагрузка
                    ff['temp'] += random.uniform(0.2, 0.6)
                    ff['pulse'] += random.randint(2, 6)
                else:
                    # ДВИЖЕНИЕ
                    ff['action'] = 'moving'
                    if ff['x'] < fx: ff['x'] += 1
                    elif ff['x'] > fx: ff['x'] -= 1
                    
                    if ff['y'] < fy: ff['y'] += 1
                    elif ff['y'] > fy: ff['y'] -= 1
                    
                    ff['pulse'] += random.randint(0, 3)
            else:
                # ОТДЫХ / ПАТРУЛЬ
                ff['action'] = 'patrolling'
                ff['temp'] = max(36.6, ff['temp'] - 0.2)
                ff['pulse'] = max(70, ff['pulse'] - 3)

            # Проверка лимитов (чтобы не умереть мгновенно)
            ff['pulse'] = min(210, ff['pulse'])
            
            # Анализ состояния
            if ff['temp'] > 50 and ff['pulse'] > 140:
                ff['status'] = 'CRITICAL'
            elif ff['temp'] > 42 or ff['pulse'] > 160:
                ff['status'] = 'WARNING'
            else:
                ff['status'] = 'OK'
            
            sensors_buffer.append([timestamp, ff['squad'], ff['id'], round(ff['temp'],1), ff['pulse'], ff['status'], ff['x'], ff['y']])

        # 3. Запись логов (пакетная запись эффективнее)
        try:
            with open(SENSOR_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(sensors_buffer)
            
            if events_buffer:
                with open(EVENT_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(events_buffer)
        except Exception as e:
            print(f"Ошибка записи логов: {e}")

        time.sleep(1)

# Запуск потока симуляции
sim_thread = threading.Thread(target=simulation_tick, daemon=True)
sim_thread.start()

# --- WEB МАРШРУТЫ ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    return jsonify({'grid': fire_grid, 'firefighters': firefighters})

@app.route('/api/spark', methods=['POST'])
def spark():
    data = request.json
    x, y = data.get('x', random.randint(0, GRID_SIZE-1)), data.get('y', random.randint(0, GRID_SIZE-1))
    fire_grid[y][x] = 80 # Сразу сильный очаг
    return jsonify({'status': 'fire started'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)