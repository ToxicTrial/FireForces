import math
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

def _degrees_to_meters(lat_diff, lon_diff, lat_origin):
    """Преобразует разницу широты/долготы в метры (приближённо)."""

    meters_per_deg_lat = 111_320  # средняя величина
    meters_per_deg_lon = 111_320 * math.cos(math.radians(lat_origin))
    return lat_diff * meters_per_deg_lat, lon_diff * meters_per_deg_lon


def _meters_to_degrees(dx, dy, lat_origin):
    """Преобразует сдвиг по метрам в градусы широты/долготы (приближённо)."""

    meters_per_deg_lat = 111_320
    meters_per_deg_lon = 111_320 * math.cos(math.radians(lat_origin))
    return dy / meters_per_deg_lat, dx / meters_per_deg_lon


def haversine_distance(lat1, lon1, lat2, lon2):
    """Возвращает расстояние между двумя точками в метрах (приближённо)."""

    dx_lat, dx_lon = _degrees_to_meters(lat2 - lat1, lon2 - lon1, (lat1 + lat2) / 2)
    return math.hypot(dx_lat, dx_lon)


# ===== Начальные сценарии пожара и бойцов =====
def create_initial_fires():
    fires_cfg = config.get("fires")
    fires_list = []
    if isinstance(fires_cfg, list) and fires_cfg:
        for i, f in enumerate(fires_cfg, start=1):
            lat = f.get("lat", center_lat + random.uniform(-0.002, 0.002))
            lon = f.get("lon", center_lon + random.uniform(-0.002, 0.002))
            fires_list.append({
                "id": f.get("id", i),
                "name": f.get("name", f"Очаг {i}"),
                "lat": float(lat),
                "lon": float(lon),
                "radius": float(f.get("radius", 60.0)),  # метры
                "intensity": float(f.get("intensity", 80.0)),
                "spread_rate": float(f.get("spread_rate", 0.8)),  # м/с
                "decay_rate": float(f.get("decay_rate", 0.05)),  # снижение интенсивности за секунду
                "active": True,
            })
    else:
        # Один очаг рядом с центром
        fires_list.append({
            "id": 1,
            "name": "Очаг 1",
            "lat": center_lat + 0.001,
            "lon": center_lon,
            "radius": 70.0,
            "intensity": 90.0,
            "spread_rate": 0.9,
            "decay_rate": 0.05,
            "active": True,
        })
    return fires_list


def create_initial_units():
    units_list = []
    if "firefighters" in config and isinstance(config["firefighters"], list):
        base_units = config["firefighters"]
    else:
        base_units = []
        for i in range(5):
            base_units.append({
                "name": f"Боец {i+1}",
                "lat": center_lat + random.uniform(-0.005, 0.005),
                "lon": center_lon + random.uniform(-0.005, 0.005),
            })

    for i, unit in enumerate(base_units, start=1):
        name = unit.get("name") or f"Боец {i}"
        lat = unit.get("lat", center_lat)
        lon = unit.get("lon", center_lon)
        units_list.append({
            "name": name,
            "lat": float(lat),
            "lon": float(lon),
            "temp": 22.0,
            "pulse": 75.0,
            "moving": True,
            "status": "на выезде",
            "target_fire": None,
        })
    return units_list


fires = create_initial_fires()
units = create_initial_units()

def choose_target_fire(unit, fires_list):
    """Назначает ближайший активный пожар в качестве цели."""

    active_fires = [f for f in fires_list if f["active"]]
    if not active_fires:
        unit["target_fire"] = None
        unit["status"] = "ожидание"
        return None

    closest = min(active_fires, key=lambda f: haversine_distance(unit["lat"], unit["lon"], f["lat"], f["lon"]))
    unit["target_fire"] = closest["id"]
    return closest


def update_fires(fires_list, units_list, dt_seconds=5):
    """Распространение и ослабление очагов с учётом работы бойцов."""

    for fire in fires_list:
        if not fire["active"]:
            continue

        # Расширение радиуса от ветра/топлива
        fire["radius"] += fire["spread_rate"] * dt_seconds

        # Снижение интенсивности от естественного выгорания
        fire["intensity"] = max(0.0, fire["intensity"] - fire["decay_rate"] * dt_seconds)

        # Если рядом работают бойцы – активное тушение
        engaged_units = [u for u in units_list if u.get("target_fire") == fire["id"]]
        for u in engaged_units:
            distance = haversine_distance(u["lat"], u["lon"], fire["lat"], fire["lon"])
            if distance <= fire["radius"] + 5:
                # Чем ближе, тем сильнее влияние
                suppression = max(0.5, (fire["radius"] - distance) / max(fire["radius"], 1))
                fire["intensity"] = max(0.0, fire["intensity"] - suppression * dt_seconds * 2)

        if fire["intensity"] <= 1.0:
            fire["active"] = False
            fire["radius"] = max(fire["radius"], 20.0)

    return fires_list


def update_units(units_list, fires_list, dt_seconds=5):
    """Обновляет координаты и показатели бойцов исходя из симуляции пожара."""

    speed_m_s = 1.2  # средняя скорость движения
    engage_distance = 25.0
    ambient_temp = 22.0

    for u in units_list:
        fire = choose_target_fire(u, fires_list)

        if fire is None:
            u["moving"] = False
            u["temp"] = ambient_temp
            u["pulse"] = max(60.0, u.get("pulse", 70.0) - 1)
            continue

        distance = haversine_distance(u["lat"], u["lon"], fire["lat"], fire["lon"])
        lat = u["lat"]
        lon = u["lon"]

        if distance > engage_distance:
            # Двигаемся к цели
            step = min(speed_m_s * dt_seconds, distance)
            dy = fire["lat"] - lat
            dx = fire["lon"] - lon
            dy_m, dx_m = _degrees_to_meters(dy, dx, lat)
            if dx_m == 0 and dy_m == 0:
                unit_dir_x = unit_dir_y = 0
            else:
                length = math.hypot(dx_m, dy_m)
                unit_dir_x = dx_m / length
                unit_dir_y = dy_m / length
            step_dx = unit_dir_x * step
            step_dy = unit_dir_y * step
            delta_lat, delta_lon = _meters_to_degrees(step_dx, step_dy, lat)
            u["lat"] += delta_lon
            u["lon"] += delta_lat
            u["moving"] = True
            u["status"] = "следует к очагу"
        else:
            u["moving"] = False
            u["status"] = "работает у очага"

        # Тепловое воздействие и нагрузка
        heat_factor = max(0.0, fire["intensity"] * max(0.0, (fire["radius"] - distance) / max(fire["radius"], 1)))
        exertion = 5.0 if u["moving"] else 2.0
        u["temp"] = min(80.0, ambient_temp + heat_factor * 0.6 + exertion)

        pulse_base = 70.0
        u["pulse"] = min(190.0, pulse_base + heat_factor * 0.8 + (15.0 if u["moving"] else 8.0))

    return units_list

# ===== Функция для создания и сохранения карты с текущими данными =====
def create_map(units_list, fires_list):
    """Создаёт интерактивную карту с маркерами для каждого бойца и контурами пожара."""
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
    # Добавляем мета-теги в <head> для автообновления и отключения кеширования
    meta_tags = (
        '<meta http-equiv="refresh" content="5" />'  # авто-обновление страницы каждые 5 сек
        '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>'
        '<meta http-equiv="Pragma" content="no-cache"/>'
        '<meta http-equiv="Expires" content="0"/>'
    )
    m.get_root().header.add_child(Element(meta_tags))

    # Рисуем границы очагов
    for fire in fires_list:
        color = "red" if fire["active"] else "gray"
        folium.Circle(
            location=[fire["lat"], fire["lon"]],
            radius=fire["radius"],
            color=color,
            fill=True,
            fill_opacity=0.25,
            popup=(f"{fire['name']}<br>Радиус: {int(fire['radius'])} м<br>"
                   f"Интенсивность: {fire['intensity']:.1f}<br>"
                   f"Статус: {'активен' if fire['active'] else 'ликвидирован'}"),
        ).add_to(m)

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
        status_text = u.get("status") or ("движется" if u["moving"] else "неподвижен")
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
    # (Опционально) можно добавить отображение времени обновления
    now = time.strftime("%H:%M:%S")
    title_html = (f'<div style="position: fixed; top: 10px; left: 10px; z-index: 1000; '
                  f'background-color: white; padding: 5px; font-size: 14px;">'
                  f'Обновлено: {now}'
                  f'</div>')
    m.get_root().html.add_child(Element(title_html))
    # Сохраняем карту в HTML-файл
    m.save("map.html")

# ===== Запуск отображения карты и цикла обновления =====
create_map(units, fires)
webbrowser.open("file://" + os.path.abspath("map.html"))
print("Карта открыта в браузере. Запущена симуляция работы подразделений... (Ctrl+C для остановки)")

tick_seconds = 5

try:
    while True:
        time.sleep(tick_seconds)
        fires = update_fires(fires, units, dt_seconds=tick_seconds)
        units = update_units(units, fires, dt_seconds=tick_seconds)
        create_map(units, fires)
except KeyboardInterrupt:
    print("\nОстановка симуляции. Скрипт завершён.")