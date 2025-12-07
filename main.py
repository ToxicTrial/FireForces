import os, time, random, json, webbrowser
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

# Список бойцов (инициализация либо из конфига, либо генерация случайных)
units = []
if "firefighters" in config and isinstance(config["firefighters"], list):
    for i, unit in enumerate(config["firefighters"]):
        name = unit.get("name") or f"Боец {i+1}"
        # Координаты: обязательны для отображения; если нет, используем центр + случайное смещение
        lat = unit.get("lat")
        lon = unit.get("lon")
        if lat is None or lon is None:
            # небольшое случайное смещение от центра, ~в пределах нескольких сотен метров
            lat = center_lat + random.uniform(-0.005, 0.005)
            lon = center_lon + random.uniform(-0.005, 0.005)
        # Температура и пульс: если не заданы, генерируем начальные значения
        temp = unit.get("temp")
        if temp is None:
            temp = random.uniform(20, 40)  # начальная температура окружающей среды, градусы Цельсия
        pulse = unit.get("pulse")
        if pulse is None:
            pulse = random.randint(60, 100)  # начальный пульс
        moving = unit.get("moving")
        if moving is None:
            moving = bool(random.getrandbits(1))  # случайно движется или нет
        units.append({
            "name": name,
            "lat": float(lat),
            "lon": float(lon),
            "temp": float(temp),
            "pulse": float(pulse),
            "moving": bool(moving)
        })
else:
    # Если конфигурация не задана, создаём 5 бойцов с случайными начальными параметрами
    for i in range(5):
        name = f"Боец {i+1}"
        # размещаем вокруг центра в пределах ~0.005 градуса (порядка нескольких сотен метров)
        lat = center_lat + random.uniform(-0.005, 0.005)
        lon = center_lon + random.uniform(-0.005, 0.005)
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

# ===== Функция для создания и сохранения карты с текущими данными =====
def create_map(units_list):
    """Создаёт интерактивную карту с маркерами для каждого бойца и сохраняет в файл map.html."""
    # Создаём карту Folium, центрируем на заданных координатах
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
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
# Сначала создаём начальную карту и открываем её в браузере
create_map(units)
# Открываем файл карты в браузере по умолчанию
webbrowser.open("file://" + os.path.abspath("map.html"))
print("Карта открыта в браузере. Идёт имитация... (нажмите Ctrl+C для остановки)")

# Главный цикл: обновление данных и карты каждые 5 секунд
try:
    while True:
        time.sleep(5)            # ждем 5 секунд
        units = update_units(units)  # обновляем параметры бойцов
        create_map(units)        # создаём и сохраняем новую карту с обновленными данными
        # (браузер автоматически перезагрузит страницу благодаря meta refresh)
except KeyboardInterrupt:
    print("\nОстановка симуляции. Скрипт завершён.")
