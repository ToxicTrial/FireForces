import os
import time
import random
import json
import webbrowser

import folium
from folium import Element

# Попробуем подключить PyYAML для чтения YAML (если не установлен, скрипт продолжит без него)
try:
    import yaml
except ImportError:
    yaml = None

# ===== Чтение конфигурации (если файл config.json или config.yaml существует) =====
config = {}
if os.path.exists("config.yaml") and yaml is not None:
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
elif os.path.exists("config.json"):
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

# Центр карты (если указан в конфиге, иначе задаём по умолчанию)
if "center" in config and isinstance(config["center"], (list, tuple)) and len(config["center"]) == 2:
    center_lat, center_lon = config["center"]
else:
    # Координаты по умолчанию (например, центр Москвы)
    center_lat, center_lon = 55.751244, 37.618423


def select_operational_area(default_lat, default_lon):
    """
    Позволяет выбрать область работы (один пожар/РТП) перед стартом симуляции.
    Возвращает словарь с границами и центром.
    """

    def build_area(north, south, west, east):
        return {
            "north": north,
            "south": south,
            "west": west,
            "east": east,
            "center_lat": (north + south) / 2,
            "center_lon": (west + east) / 2,
        }

    def default_area(lat, lon):
        # Квадрат ~1 км вокруг точки (0.01 градуса ≈ 1.1 км)
        return build_area(lat + 0.01, lat - 0.01, lon - 0.01, lon + 0.01)

    print("=== Выбор участка местности для конкретного пожара ===")
    print("Для каждого РТП можно выбрать отдельный участок. \n"
          "По умолчанию берётся квадрат ~1 км вокруг центра карты.")
    try:
        use_custom = input("Задать участок вручную? (y/N): ").strip().lower()
    except EOFError:
        use_custom = ""

    if use_custom == "y":
        try:
            north = float(input("Введите северную границу (широта): "))
            south = float(input("Введите южную границу (широта): "))
            west = float(input("Введите западную границу (долгота): "))
            east = float(input("Введите восточную границу (долгота): "))
            if north <= south or east <= west:
                print("Границы заданы некорректно. Используем значения по умолчанию.")
                return default_area(default_lat, default_lon)
            return build_area(north, south, west, east)
        except (ValueError, EOFError):
            print("Не удалось разобрать координаты. Используем участок по умолчанию.")
            return default_area(default_lat, default_lon)
    else:
        return default_area(default_lat, default_lon)


operational_area = select_operational_area(center_lat, center_lon)
center_lat, center_lon = operational_area["center_lat"], operational_area["center_lon"]

# Список бойцов (инициализация либо из конфига, либо генерация случайных)
units = []
if "firefighters" in config and isinstance(config["firefighters"], list):
    for i, unit in enumerate(config["firefighters"]):
        name = unit.get("name") or f"Боец {i+1}"
        lat = unit.get("lat")
        lon = unit.get("lon")
        if lat is None or lon is None:
            lat = random.uniform(operational_area["south"], operational_area["north"])
            lon = random.uniform(operational_area["west"], operational_area["east"])
        temp = unit.get("temp")
        if temp is None:
            temp = random.uniform(20, 40)
        pulse = unit.get("pulse")
        if pulse is None:
            pulse = random.randint(60, 100)
        moving = unit.get("moving")
        if moving is None:
            moving = bool(random.getrandbits(1))
        units.append({
            "name": name,
            "lat": float(lat),
            "lon": float(lon),
            "temp": float(temp),
            "pulse": float(pulse),
            "moving": bool(moving)
        })
else:
    # Если конфигурация не задана, создаём 5 бойцов с случайными начальными параметрами внутри участка
    for i in range(5):
        name = f"Боец {i+1}"
        lat = random.uniform(operational_area["south"], operational_area["north"])
        lon = random.uniform(operational_area["west"], operational_area["east"])
        temp = random.uniform(20, 40)    # стартовая температура (°C)
        pulse = random.randint(60, 100)  # стартовый пульс
        moving = True  # по умолчанию считаем, что движется
        units.append({"name": name, "lat": lat, "lon": lon, "temp": temp, "pulse": pulse, "moving": moving})


# ===== Функция для обновления состояния бойцов (имитация датчиков и движения) =====
def update_units(units_list):
    """Обновляет параметры каждого бойца: координаты, температуру, пульс, статус движения."""
    for u in units_list:
        # С небольшим шансом переключаем статус движения (начал двигаться или остановился)
        if random.random() < 0.1:
            u["moving"] = not u["moving"]
        if u["moving"]:
            # Если боец движется, смещаем координаты случайно (шагаем на небольшое расстояние)
            u["lat"] += random.uniform(-0.0005, 0.0005)
            u["lon"] += random.uniform(-0.0005, 0.0005)
        # Не выходим за границы выбранного участка
        u["lat"] = max(min(u["lat"], operational_area["north"]), operational_area["south"])
        u["lon"] = max(min(u["lon"], operational_area["east"]), operational_area["west"])
        # Обновляем температуру: небольшие случайные колебания
        u["temp"] += random.uniform(-0.5, 0.5)
        # Не даём температуре упасть ниже 0
        if u["temp"] < 0:
            u["temp"] = 0
        # С вероятностью 5% имитируем резкий скачок температуры выше порога (например, попадание в огонь)
        if u["temp"] < 55 and random.random() < 0.05:
            u["temp"] = random.uniform(61, 80)
        # Если температура уже высокая, с шансом 10% "остывает" ниже порога
        if u["temp"] > 60 and random.random() < 0.1:
            u["temp"] = random.uniform(40, 55)
        # Обновляем пульс: если движется, может повышаться, если нет – немного снижаться
        if u["moving"]:
            u["pulse"] += random.randint(0, 5)
        else:
            u["pulse"] -= random.randint(0, 3)
        # Небольшое случайное колебание пульса
        u["pulse"] += random.randint(-2, 2)
        # Ограничиваем пульс реалистичными пределами
        if u["pulse"] < 40:
            u["pulse"] = 40
        if u["pulse"] > 200:
            u["pulse"] = 200
        # С 5% вероятностью — всплеск пульса (выше порога 140, если до сих пор низкий)
        if u["pulse"] < 130 and random.random() < 0.05:
            u["pulse"] = random.randint(145, 170)
        # Если пульс высок (тревога), с 10% шансом спад до нормального уровня (имитация отдыха/остывания)
        if u["pulse"] > 140 and random.random() < 0.1:
            u["pulse"] = random.randint(80, 120)
    return units_list


def simulate_fire_spread(area, origin, base_growth=0.003):
    """Имитация прогноза распространения огня по направлениям с поправкой на ветер."""

    def wind_modifier(direction_name):
        wind_dir = (config.get("wind_direction") or "N").upper()
        speed = float(config.get("wind_speed_kmh") or 10)
        # Простая шкала влияния ветра: направление совпадает с ветром -> +100% при сильном ветре,
        # боковые направления получают меньший бонус.
        main_map = {
            "N": "N",
            "NE": "NE",
            "E": "E",
            "SE": "SE",
            "S": "S",
            "SW": "SW",
            "W": "W",
            "NW": "NW",
        }
        target = main_map.get(wind_dir, "N")
        if direction_name == target:
            return 1 + min(speed / 20, 1.0)  # до +100% при сильном ветре
        if direction_name in (target + "E", target + "W") or target in (direction_name + "E", direction_name + "W"):
            return 1 + min(speed / 50, 0.4)  # боковое влияние
        return 1

    direction_vectors = {
        "N": (0, 1),
        "NE": (1, 1),
        "E": (1, 0),
        "SE": (1, -1),
        "S": (0, -1),
        "SW": (-1, -1),
        "W": (-1, 0),
        "NW": (-1, 1),
    }

    predictions = []
    for direction, (dx, dy) in direction_vectors.items():
        growth = base_growth * (0.5 + random.random()) * wind_modifier(direction)
        dest_lat = origin[0] + dy * growth
        dest_lon = origin[1] + dx * growth
        # Обрезаем прогноз до выбранного участка
        dest_lat = max(min(dest_lat, area["north"]), area["south"])
        dest_lon = max(min(dest_lon, area["east"]), area["west"])
        predictions.append({
            "direction": direction,
            "intensity": growth,
            "dest": (dest_lat, dest_lon),
        })

    predictions.sort(key=lambda x: x["intensity"], reverse=True)
    return predictions


def suggest_unit_allocation(units_list, predictions):
    """Рекомендует распределение подразделений по направлениям наиболее вероятного роста огня."""
    if not predictions:
        return {}

    top_directions = [p["direction"] for p in predictions[:3]]
    allocations = {d: [] for d in top_directions}
    for idx, unit in enumerate(units_list):
        direction = top_directions[idx % len(top_directions)]
        allocations[direction].append(unit["name"])
    return allocations


# ===== Функция для создания и сохранения карты с текущими данными =====
def create_map(units_list, predictions, allocations):
    """Создаёт интерактивную карту с маркерами для бойцов, прогнозом и сохраняет в файл map.html."""
    # Создаём карту Folium, центрируем на выбранном участке
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15)
    folium.Rectangle(
        bounds=[
            [operational_area["north"], operational_area["west"]],
            [operational_area["south"], operational_area["east"]],
        ],
        color="orange",
        fill=True,
        fill_opacity=0.05,
        weight=2,
        tooltip="Рабочий участок",
    ).add_to(m)

    # Добавляем мета-теги в <head> для автообновления и отключения кеширования
    meta_tags = (
        '<meta http-equiv="refresh" content="5" />'  # авто-обновление страницы каждые 5 сек
        '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>'
        '<meta http-equiv="Pragma" content="no-cache"/>'
        '<meta http-equiv="Expires" content="0"/>'
    )
    m.get_root().header.add_child(Element(meta_tags))
    # Добавляем маркер для каждого пожарного
    for u in units_list:
        # Проверяем пороги для определения тревоги
        alert_temp = u["temp"] > 60.0
        alert_pulse = u["pulse"] > 140.0
        # Выбираем цвет маркера: красный при тревоге, зелёный если движется, синий если стоит (без тревог)
        if alert_temp or alert_pulse:
            color = "red"
        else:
            color = "green" if u["moving"] else "blue"
        # Значок маркера (иконка): используем стандартный "user" (можно заменить на другую подходящую иконку)
        icon = folium.Icon(color=color, icon="user")
        # Статус движения текстом
        status_text = "движется" if u["moving"] else "неподвижен"
        # Подготовка текста для тревоги
        alerts = []
        if alert_temp:
            alerts.append("Высокая температура!")
        if alert_pulse:
            alerts.append("Высокий пульс!")
        alert_text = ", ".join(alerts) if alerts else "нет"
        # Формируем HTML для всплывающего окна (popup)
        popup_html = (f"<b>{u['name']}</b><br>"
                      f"Температура: {u['temp']:.1f} °C<br>"
                      f"Пульс: {int(u['pulse'])} уд/мин<br>"
                      f"Статус: {status_text}<br>"
                      f"Тревоги: {alert_text}")
        folium.Marker(location=[u["lat"], u["lon"]], icon=icon, popup=popup_html).add_to(m)

    # Маркер очага пожара (центр участка)
    folium.Marker(
        location=[operational_area["center_lat"], operational_area["center_lon"]],
        icon=folium.Icon(color="orange", icon="fire"),
        popup="Очаг пожара",
    ).add_to(m)

    # Визуализация прогноза распространения
    colors = ["red", "darkred", "orange", "darkorange", "purple", "darkpurple", "cadetblue", "blue"]
    for idx, pred in enumerate(predictions):
        folium.PolyLine(
            locations=[
                [operational_area["center_lat"], operational_area["center_lon"]],
                [pred["dest"][0], pred["dest"][1]],
            ],
            color=colors[idx % len(colors)],
            weight=4,
            tooltip=f"Направление {pred['direction']}: прогноз роста {pred['intensity']*1000:.1f} м",
        ).add_to(m)

    # Блок рекомендаций по распределению
    allocation_lines = []
    for direction, names in allocations.items():
        if names:
            allocation_lines.append(f"{direction}: {', '.join(names)}")
    allocation_text = "<br>".join(allocation_lines) if allocation_lines else "Нет данных о распределении"

    # (Опционально) можно добавить отображение времени обновления
    now = time.strftime("%H:%M:%S")
    title_html = (f'<div style="position: fixed; top: 10px; left: 10px; z-index: 1000; '
                  f'background-color: white; padding: 5px; font-size: 14px;">'
                  f'Обновлено: {now}<br>'
                  f'Рекомендации:<br>{allocation_text}'
                  f'</div>')
    m.get_root().html.add_child(Element(title_html))
    # Сохраняем карту в HTML-файл
    m.save("map.html")


# ===== Запуск отображения карты и цикла обновления =====
# Сначала создаём начальную карту и открываем её в браузере
initial_predictions = simulate_fire_spread(operational_area, (center_lat, center_lon))
initial_allocations = suggest_unit_allocation(units, initial_predictions)
create_map(units, initial_predictions, initial_allocations)
# Открываем файл карты в браузере по умолчанию
webbrowser.open("file://" + os.path.abspath("map.html"))
print("Карта открыта в браузере. Идёт имитация... (нажмите Ctrl+C для остановки)")

# Главный цикл: обновление данных и карты каждые 5 секунд
try:
    while True:
        time.sleep(5)            # ждем 5 секунд
        units = update_units(units)  # обновляем параметры бойцов
        predictions = simulate_fire_spread(operational_area, (center_lat, center_lon))
        allocations = suggest_unit_allocation(units, predictions)
        create_map(units, predictions, allocations)        # создаём и сохраняем новую карту с обновленными данными
        # (браузер автоматически перезагрузит страницу благодаря meta refresh)
except KeyboardInterrupt:
    print("\nОстановка симуляции. Скрипт завершён.")