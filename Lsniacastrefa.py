import sqlite3
import shutil
import os
import datetime 
import calendar
from fpdf import FPDF


BACKUP_FOLDER = "backup_lsniacastrefa"
LAST_BACKUP_FILE = "last_backup.txt"

DB = "lsniaca_strefa.db"

# --- BAZA DANYCH ---

##liczenie dni tygodnia w miesiacu##
def count_cleanings_auto(year, month, cleaning_day, frequency):
    days_map = {
        "MON": 0,
        "TUE": 1,
        "WED": 2,
        "THU": 3,
        "FRI": 4,
        "SAT": 5,
        "SUN": 6
    }

    target_weekday = days_map.get(cleaning_day)
    if target_weekday is None:
        return 0

    count = 0
    cal = calendar.monthcalendar(year, month)

    for week in cal:
        if week[target_weekday] != 0:
            count += 1

    if frequency == 2:
        count = (count + 1) // 2

    return count


def connect():
    return sqlite3.connect(DB)

def init_db():
    conn = connect()
    c = conn.cursor()

    # --- Tabele podstawowe ---

    c.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY,
        name TEXT,
        hourly_rate REAL,
        active INTEGER,
        monthly_salary REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS objects (
        id INTEGER PRIMARY KEY,
        name TEXT,
        client TEXT,
        billing_type TEXT,
        monthly_rate REAL,
        active INTEGER,
        ryczalt REAL,
        invoice_sent INTEGER DEFAULT 0,
        invoice_paid INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS hours (
        id INTEGER PRIMARY KEY,
        employee_id INTEGER,
        object_id INTEGER,
        date TEXT,
        hours REAL,
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(object_id) REFERENCES objects(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY,
        object_id INTEGER,
        year INTEGER,
        month INTEGER,
        invoice_sent INTEGER,
        invoice_paid INTEGER,
        checklist_done INTEGER,
        FOREIGN KEY(object_id) REFERENCES objects(id)
    )
    """)

    # --- NOWE TABELĘ ---

    # Koszty dodatkowe (chemia, paliwo, maszyny, inne)
    c.execute("""
    CREATE TABLE IF NOT EXISTS other_costs (
        id INTEGER PRIMARY KEY,
        object_id INTEGER,
        date TEXT,
        category TEXT,
        description TEXT,
        amount REAL,
        FOREIGN KEY(object_id) REFERENCES objects(id)
    )
    """)

    # Dni pracownika (PRACA / URLOP / L4)
    c.execute("""
    CREATE TABLE IF NOT EXISTS employee_days (
        id INTEGER PRIMARY KEY,
        employee_id INTEGER,
        date TEXT,
        status TEXT,
        FOREIGN KEY(employee_id) REFERENCES employees(id)
    )
    """)

        # Obecność pracowników (wejście/wyjście + GPS)
    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY,
        employee_id INTEGER,
        object_id INTEGER,
        start_time TEXT,
        start_lat REAL,
        start_lon REAL,
        end_time TEXT,
        end_lat REAL,
        end_lon REAL,
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(object_id) REFERENCES objects(id)
    )
    """)

        # Szablony checklist dla obiektów
    c.execute("""
    CREATE TABLE IF NOT EXISTS checklist_templates (
        id INTEGER PRIMARY KEY,
        object_id INTEGER,
        item_name TEXT,
        FOREIGN KEY(object_id) REFERENCES objects(id)
    )
    """)

    # Wyniki checklist wykonanych przez pracowników
    c.execute("""
    CREATE TABLE IF NOT EXISTS checklist_results (
        id INTEGER PRIMARY KEY,
        object_id INTEGER,
        employee_id INTEGER,
        date TEXT,
        item_name TEXT,
        status TEXT,
        FOREIGN KEY(object_id) REFERENCES objects(id),
        FOREIGN KEY(employee_id) REFERENCES employees(id)
    )
    """)

        # Zgłoszenia usterek
    c.execute("""
    CREATE TABLE IF NOT EXISTS issues (
        id INTEGER PRIMARY KEY,
        object_id INTEGER,
        employee_id INTEGER,
        description TEXT,
        photo_path TEXT,
        status TEXT,
        created_at TEXT,
        resolved_at TEXT,
        FOREIGN KEY(object_id) REFERENCES objects(id),
        FOREIGN KEY(employee_id) REFERENCES employees(id)
    )
    """)



    conn.commit()
    conn.close()

    
    ##backup##

def daily_backup():
    # Utwórz folder backupu, jeśli nie istnieje
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)

    # Dzisiejsza data
    today = datetime.datetime.today().strftime("%Y-%m-%d")

    # Nazwa pliku backupu
    backup_name = f"lsniaca_strefa_{today}.db"
    backup_path = os.path.join(BACKUP_FOLDER, backup_name)

    # Sprawdź, czy backup z dzisiejszą datą już istnieje
    if os.path.exists(backup_path):
        print(f"[BACKUP] Backup z dzisiejszą datą już istnieje: {backup_path}")
        return

    # Kopiowanie bazy danych
    shutil.copyfile(DB, backup_path)

    print(f"[BACKUP] Utworzono kopię: {backup_path}")

#start Pracy##
def start_attendance():
    print("\n--- Rozpoczęcie pracy ---")

    list_employees()
    emp_id = input_int("ID pracownika: ")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    # GPS będzie wysyłany z aplikacji mobilnej
    lat = None
    lon = None

    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    c = conn.cursor()

    # Sprawdź, czy pracownik nie ma już otwartej obecności
    c.execute("""
        SELECT id FROM attendance
        WHERE employee_id = ? AND end_time IS NULL
    """, (emp_id,))
    open_row = c.fetchone()

    if open_row:
        print("Ten pracownik już jest w pracy! Najpierw zakończ poprzednią obecność.\n")
        conn.close()
        return

    c.execute("""
        INSERT INTO attendance (employee_id, object_id, start_time, start_lat, start_lon)
        VALUES (?, ?, ?, ?, ?)
    """, (emp_id, obj_id, start_time, lat, lon))

    conn.commit()
    conn.close()

    print(f"Pracownik {emp_id} rozpoczął pracę na obiekcie {obj_id} o {start_time}.\n")

##koniec pracy##
def end_attendance():
    print("\n--- Zakończenie pracy ---")

    list_employees()
    emp_id = input_int("ID pracownika: ")

    conn = connect()
    c = conn.cursor()

    # Pobierz otwartą obecność
    c.execute("""
        SELECT id, object_id, start_time
        FROM attendance
        WHERE employee_id = ? AND end_time IS NULL
    """, (emp_id,))
    row = c.fetchone()

    if not row:
        print("Ten pracownik nie ma aktywnej obecności.\n")
        conn.close()
        return

    att_id, obj_id, start_time = row

    end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    end_lat = None
    end_lon = None

    c.execute("""
        UPDATE attendance
        SET end_time = ?, end_lat = ?, end_lon = ?
        WHERE id = ?
    """, (end_time, end_lat, end_lon, att_id))

    conn.commit()
    conn.close()

    print(f"Pracownik {emp_id} zakończył pracę na obiekcie {obj_id} o {end_time}.\n")

##lista wejsc/wyjsc##
def list_attendance():
    conn = connect()
    c = conn.cursor()

    print("\n--- Lista obecności ---")
    c.execute("""
        SELECT a.id, e.name, o.name, a.start_time, a.end_time
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        JOIN objects o ON a.object_id = o.id
        ORDER BY a.start_time DESC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak zapisanej obecności.\n")
        return

    for r in rows:
        att_id, emp_name, obj_name, start, end = r
        end_info = end if end else "W TRAKCIE"
        print(f"{att_id}: {emp_name} | {obj_name} | start: {start} | koniec: {end_info}")

    print("------------------------\n")

##raport obecnosci##
def raport_obecnosci():
    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    conn = connect()
    c = conn.cursor()

    print(f"\n=== RAPORT OBECNOŚCI {year}-{month:02d} ===\n")

    c.execute("""
        SELECT e.name, o.name, a.start_time, a.end_time
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        JOIN objects o ON a.object_id = o.id
        WHERE strftime('%Y-%m', a.start_time) = ?
        ORDER BY a.start_time
    """, (f"{year}-{month:02d}",))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak obecności w tym miesiącu.\n")
        return

    for r in rows:
        emp, obj, start, end = r
        end_info = end if end else "W TRAKCIE"
        print(f"{emp} | {obj} | {start} -> {end_info}")

    print("\n=== KONIEC RAPORTU ===\n")

##raport taskow##

def raport_tasks():
    print("\n--- RAPORT ZADAŃ ---")

    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT t.id, t.title, t.priority, t.status, t.deadline,
               o.name, e.name, t.created_at, t.completed_at
        FROM tasks t
        LEFT JOIN objects o ON t.object_id = o.id
        LEFT JOIN employees e ON t.employee_id = e.id
        WHERE strftime('%Y-%m', t.created_at) = ?
        ORDER BY t.status, t.priority DESC, t.deadline
    """, (f"{year}-{month:02d}",))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak zadań w tym miesiącu.\n")
        return

    print(f"\n=== RAPORT ZADAŃ {year}-{month:02d} ===\n")

    for r in rows:
        task_id, title, prio, status, deadline, obj, emp, created, completed = r
        obj_info = obj if obj else "Brak obiektu"
        emp_info = emp if emp else "Nieprzypisane"
        deadline_info = deadline if deadline else "brak"
        completed_info = completed if completed else "NIEUKOŃCZONE"

        print(f"{task_id}: [{status}] {title}")
        print(f"    Obiekt: {obj_info}")
        print(f"    Pracownik: {emp_info}")
        print(f"    Priorytet: {prio}")
        print(f"    Termin: {deadline_info}")
        print(f"    Utworzone: {created}")
        print(f"    Zakończone: {completed_info}")
        print()

    print("=== KONIEC RAPORTU ===\n")

##raport usterek##
 
def raport_issues():
    print("\n--- RAPORT USTEREK ---")

    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT i.id, o.name, e.name, i.description, i.status,
               i.created_at, i.resolved_at
        FROM issues i
        JOIN objects o ON i.object_id = o.id
        JOIN employees e ON i.employee_id = e.id
        WHERE strftime('%Y-%m', i.created_at) = ?
        ORDER BY i.status, i.created_at DESC
    """, (f"{year}-{month:02d}",))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak usterek w tym miesiącu.\n")
        return

    print(f"\n=== RAPORT USTEREK {year}-{month:02d} ===\n")

    for r in rows:
        issue_id, obj, emp, desc, status, created, resolved = r
        resolved_info = resolved if resolved else "NIEZAMKNIĘTA"

        print(f"{issue_id}: [{status}] Obiekt: {obj} | Zgłosił: {emp}")
        print(f"    Opis: {desc}")
        print(f"    Utworzono: {created}")
        print(f"    Zakończono: {resolved_info}")
        print()

    print("=== KONIEC RAPORTU ===\n")

def raport_checklist_extended():
    print("\n--- RAPORT CHECKLIST (rozszerzony) ---")

    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT o.name, e.name, cr.date, cr.item_name, cr.status
        FROM checklist_results cr
        JOIN objects o ON cr.object_id = o.id
        JOIN employees e ON cr.employee_id = e.id
        WHERE strftime('%Y-%m', cr.date) = ?
        ORDER BY cr.date, o.name
    """, (f"{year}-{month:02d}",))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak checklist w tym miesiącu.\n")
        return

    print(f"\n=== RAPORT CHECKLIST {year}-{month:02d} ===\n")

    for obj, emp, date, item, status in rows:
        print(f"{date} | {obj} | {emp} | {item} | {status}")

    print("\n=== KONIEC RAPORTU ===\n")

def raport_rentownosci():
    print("\n--- RAPORT RENTOWNOŚCI OBIEKTÓW ---")

    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    report, total_rev, total_cost, total_margin, total_margin_pct = calc_month_report(year, month)

    if not report:
        print("Brak danych.\n")
        return

    # Sortowanie
    sorted_by_margin = sorted(report, key=lambda x: x["margin"], reverse=True)

    print(f"\n=== TOP 5 NAJLEPSZYCH OBIEKTÓW {year}-{month:02d} ===\n")
    for r in sorted_by_margin[:5]:
        print(f"{r['object']} | marża: {r['margin']:.2f} PLN | {r['margin_pct']:.1f}%")

    print(f"\n=== TOP 5 NAJGORSZYCH OBIEKTÓW {year}-{month:02d} ===\n")
    for r in sorted_by_margin[-5:]:
        print(f"{r['object']} | marża: {r['margin']:.2f} PLN | {r['margin_pct']:.1f}%")

    print("\n=== KONIEC RAPORTU ===\n")

def dashboard():
    print("\n=== DASHBOARD MENEDŻERSKI ===")

    today = datetime.datetime.today()
    year = today.year
    month = today.month

    report, total_rev, total_cost, total_margin, total_margin_pct = calc_month_report(year, month)

    print(f"\n>>> MIESIĄC: {year}-{month:02d}")
    print(f"Przychód: {total_rev:.2f} PLN")
    print(f"Koszt: {total_cost:.2f} PLN")
    print(f"Marża: {total_margin:.2f} PLN ({total_margin_pct:.1f}%)")

    # Liczba zadań
    conn = connect()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM tasks WHERE status = 'OPEN'")
    open_tasks = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM issues WHERE status = 'OPEN'")
    open_issues = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM attendance WHERE end_time IS NULL")
    active_workers = c.fetchone()[0]

    conn.close()

    print(f"\nOtwarte zadania: {open_tasks}")
    print(f"Otwarte usterki: {open_issues}")
    print(f"Pracownicy w pracy: {active_workers}")

    print("\n=== KONIEC DASHBOARDU ===\n")

    


# --- POMOCNICZE ---

def input_int(prompt):
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Podaj liczbę całkowitą.")

def input_float(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Podaj liczbę (np. 25.5).")

def yes_no(prompt):
    v = input(prompt + " (t/n): ").strip().lower()
    return v == "t"
# --- PRACOWNICY ---

def add_employee():
    conn = connect()
    c = conn.cursor()

    name = input("Imię i nazwisko: ")

    print("Typ pracownika:")
    print("1. Rozliczany godzinowo")
    print("2. Etat (miesięczna pensja)")
    choice = input("Wybierz opcję: ")

    if choice == "1":
        hourly_rate = input_float("Stawka godzinowa (PLN): ")
        monthly_salary = None
    elif choice == "2":
        monthly_salary = input_float("Miesięczna pensja (PLN): ")
        hourly_rate = None
    else:
        print("Nieprawidłowy wybór.")
        return

    c.execute(
        "INSERT INTO employees (name, hourly_rate, monthly_salary, active) VALUES (?, ?, ?, 1)",
        (name, hourly_rate, monthly_salary)
    )

    conn.commit()
    conn.close()
    print("Dodano pracownika.\n")



def list_employees():
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT id, name, hourly_rate, monthly_salary, active FROM employees ORDER BY id")
    rows = c.fetchall()
    conn.close()

    print("\n--- Lista pracowników ---")
    for r in rows:
        emp_id, name, hourly_rate, monthly_salary, active = r
        status = "AKTYWNY" if active == 1 else "NIEAKTYWNY"

        if monthly_salary is not None:
            pay_info = f"{monthly_salary} PLN/mies."
        else:
            pay_info = f"{hourly_rate} PLN/h"

        print(f"{emp_id}: {name} | {pay_info} | {status}")

    print("-------------------------\n")

def edit_employee():
    list_employees()
    emp_id = input("Podaj ID pracownika do edycji: ")

    conn = connect()
    c = conn.cursor()

    # Pobierz aktualne dane
    c.execute("SELECT name, hourly_rate, monthly_salary, active FROM employees WHERE id = ?", (emp_id,))
    row = c.fetchone()

    if not row:
        print("Nie znaleziono pracownika.")
        conn.close()
        return

    current_name, current_hourly, current_monthly, current_active = row

    print("\n--- Edycja pracownika ---")
    print(f"1. Imię i nazwisko (obecnie: {current_name})")
    print(f"2. Stawka godzinowa (obecnie: {current_hourly})")
    print(f"3. Pensja miesięczna (obecnie: {current_monthly})")
    print(f"4. Typ pracownika (1=godzinowy, 2=etat)")
    print(f"5. Status aktywności (obecnie: {'AKTYWNY' if current_active == 1 else 'NIEAKTYWNY'})")
    print("0. Zakończ edycję")

    while True:
        choice = input("Wybierz pole do edycji: ")

        if choice == "1":
            new_name = input("Nowe imię i nazwisko: ")
            c.execute("UPDATE employees SET name = ? WHERE id = ?", (new_name, emp_id))

        elif choice == "2":
            new_rate = input_float("Nowa stawka godzinowa (PLN): ")
            c.execute("UPDATE employees SET hourly_rate = ?, monthly_salary = NULL WHERE id = ?", (new_rate, emp_id))

        elif choice == "3":
            new_salary = input_float("Nowa pensja miesięczna (PLN): ")
            c.execute("UPDATE employees SET monthly_salary = ?, hourly_rate = NULL WHERE id = ?", (new_salary, emp_id))

        elif choice == "4":
            print("1. Godzinowy")
            print("2. Etat")
            t = input("Wybierz typ: ")
            if t == "1":
                new_rate = input_float("Stawka godzinowa (PLN): ")
                c.execute("UPDATE employees SET hourly_rate = ?, monthly_salary = NULL WHERE id = ?", (new_rate, emp_id))
            elif t == "2":
                new_salary = input_float("Pensja miesięczna (PLN): ")
                c.execute("UPDATE employees SET monthly_salary = ?, hourly_rate = NULL WHERE id = ?", (new_salary, emp_id))
            else:
                print("Nieprawidłowy wybór.")

        elif choice == "5":
            print("1. Aktywny")
            print("2. Nieaktywny")
            s = input("Wybierz status: ")
            if s == "1":
                c.execute("UPDATE employees SET active = 1 WHERE id = ?", (emp_id,))
            elif s == "2":
                c.execute("UPDATE employees SET active = 0 WHERE id = ?", (emp_id,))
            else:
                print("Nieprawidłowy wybór.")

        elif choice == "0":
            break

        else:
            print("Nieprawidłowy wybór.")

        conn.commit()
        print("Zaktualizowano.\n")

    conn.close()
    print("Edycja zakończona.\n")

def raport_pracownicy():
    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    conn = connect()
    c = conn.cursor()

    # Pobieramy pracowników
    c.execute("""
        SELECT id, name, hourly_rate, monthly_salary
        FROM employees
        WHERE active = 1
    """)
    employees = c.fetchall()

    print(f"\n=== RAPORT PRACOWNIKÓW {year}-{month:02d} ===\n")

    total_hours_all = 0
    total_cost_all = 0
    total_value_all = 0

    for emp in employees:
        emp_id, name, hourly_rate, monthly_salary = emp

        # Liczymy godziny pracownika
        c.execute("""
            SELECT SUM(hours)
            FROM hours
            WHERE employee_id = ?
              AND strftime('%Y-%m', date) = ?
        """, (emp_id, f"{year}-{month:02d}"))
        hours_sum = c.fetchone()[0] or 0

        # Koszt pracownika
        if monthly_salary:
            cost = monthly_salary
        else:
            cost = hours_sum * hourly_rate

        # Wartość pracy (ile zarobił dla firmy)
        # Liczymy wartość pracy jako suma: godziny * stawka obiektu
        c.execute("""
            SELECT SUM(h.hours * o.monthly_rate)
            FROM hours h
            JOIN objects o ON h.object_id = o.id
            WHERE h.employee_id = ?
              AND strftime('%Y-%m', h.date) = ?
              AND o.billing_type = 'sprzatanie'
        """, (emp_id, f"{year}-{month:02d}"))
        value_sprzatanie = c.fetchone()[0] or 0

        # Jednorazowe mycia – wartość = stawka jednorazowa (tylko raz)
        c.execute("""
            SELECT DISTINCT o.id, o.monthly_rate
            FROM hours h
            JOIN objects o ON h.object_id = o.id
            WHERE h.employee_id = ?
              AND strftime('%Y-%m', h.date) = ?
              AND o.billing_type = 'jednorazowe'
        """, (emp_id, f"{year}-{month:02d}"))
        jednorazowe_rows = c.fetchall()
        value_jednorazowe = sum(r[1] for r in jednorazowe_rows)

        # Ryczałt nie liczy się jako wartość pracy pracownika
        value_total = value_sprzatanie + value_jednorazowe

        # Marża pracownika
        margin = value_total - cost
        margin_pct = (margin / value_total * 100) if value_total > 0 else 0

        # Dni PRACA / URLOP / L4
        c.execute("""
            SELECT status, COUNT(*)
            FROM employee_days
            WHERE employee_id = ?
              AND strftime('%Y-%m', date) = ?
            GROUP BY status
        """, (emp_id, f"{year}-{month:02d}"))
        days_map = {row[0]: row[1] for row in c.fetchall()}

        praca = days_map.get("PRACA", 0)
        urlop = days_map.get("URLOP", 0)
        l4 = days_map.get("L4", 0)

        # Wyświetlanie
        print(f"--- {name} ---")
        print(f"Godziny: {hours_sum}")
        print(f"Koszt: {cost:.2f} PLN")
        print(f"Wartość pracy: {value_total:.2f} PLN")
        print(f"Marża: {margin:.2f} PLN ({margin_pct:.1f}%)")
        print(f"Dni: PRACA={praca}, URLOP={urlop}, L4={l4}")
        print()

        # Sumy globalne
        total_hours_all += hours_sum
        total_cost_all += cost
        total_value_all += value_total

    conn.close()

    total_margin = total_value_all - total_cost_all
    total_margin_pct = (total_margin / total_value_all * 100) if total_value_all > 0 else 0

    print("=== PODSUMOWANIE ===")
    print(f"Łączne godziny: {total_hours_all}")
    print(f"Łączny koszt: {total_cost_all:.2f} PLN")
    print(f"Łączna wartość pracy: {total_value_all:.2f} PLN")
    print(f"Łączna marża: {total_margin:.2f} PLN ({total_margin_pct:.1f}%)")
    print("=====================\n")


# --- OBIEKTY / ZLECENIA ---

def add_object():
    conn = connect()
    c = conn.cursor()

    name = input("Nazwa obiektu: ")
    client = input("Adres obiektu (zamiast nazwy klienta): ")

    print("Typ rozliczenia:")
    print("1. Od sprzątania (stawka za jedno sprzątanie)")
    print("2. Ryczałt miesięczny")
    print("3. Jednorazowe mycie")
    choice = input("Wybierz opcję: ")

    billing_type = None
    monthly_rate = None
    ryczalt = None

    if choice == "1":
        billing_type = "sprzatanie"
        monthly_rate = input_float("Stawka za jedno sprzątanie (PLN): ")
    elif choice == "2":
        billing_type = "ryczalt"
        ryczalt = input_float("Kwota ryczałtu miesięcznego (PLN): ")
    elif choice == "3":
        billing_type = "jednorazowe"
        monthly_rate = input_float("Stawka za jednorazowe mycie (PLN): ")
    else:
        print("Nieprawidłowy wybór.")
        conn.close()
        return

    c.execute(
        "INSERT INTO objects (name, client, billing_type, monthly_rate, ryczalt, active) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (name, client, billing_type, monthly_rate, ryczalt)
    )

    conn.commit()
    conn.close()
    print("Dodano obiekt.\n")




def list_objects():
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT id, name, client, billing_type, monthly_rate, ryczalt, active FROM objects ORDER BY id")
    rows = c.fetchall()
    conn.close()

    print("\n--- Lista obiektów ---")
    for r in rows:
        obj_id, name, client, billing_type, monthly_rate, ryczalt, active = r
        status = "AKTYWNY" if active == 1 else "NIEAKTYWNY"

        if billing_type == "sprzatanie":
            extra = f"{monthly_rate} PLN / sprzątanie"
        elif billing_type == "ryczalt":
            extra = f"{ryczalt} PLN / mies."
        elif billing_type == "jednorazowe":
            extra = f"{monthly_rate} PLN (jednorazowe)"
        else:
            extra = "-"

        print(f"{obj_id}: {name} | adres: {client} | {billing_type} | {extra} | {status}")
    print("----------------------\n")



def edit_object():
    list_objects()
    obj_id = input("Podaj ID obiektu do edycji: ")

    conn = connect()
    c = conn.cursor()

    # Pobierz aktualne dane
    c.execute("""
        SELECT name, client, billing_type, monthly_rate, ryczalt, active
        FROM objects WHERE id = ?
    """, (obj_id,))
    row = c.fetchone()

    if not row:
        print("Nie znaleziono obiektu.")
        conn.close()
        return

    current_name, current_client, current_billing, current_rate, current_ryczalt, current_active = row

    print("\n--- Edycja obiektu ---")
    print(f"1. Nazwa obiektu (obecnie: {current_name})")
    print(f"2. Adres obiektu (obecnie: {current_client})")
    print(f"3. Typ rozliczenia (obecnie: {current_billing})")
    print(f"4. Stawka (obecnie: {current_rate})")
    print(f"5. Ryczałt (obecnie: {current_ryczalt})")
    print(f"6. Status aktywności (obecnie: {'AKTYWNY' if current_active == 1 else 'NIEAKTYWNY'})")
    print("0. Zakończ edycję")

    while True:
        choice = input("Wybierz pole do edycji: ")

        if choice == "1":
            new_name = input("Nowa nazwa obiektu: ")
            c.execute("UPDATE objects SET name = ? WHERE id = ?", (new_name, obj_id))

        elif choice == "2":
            new_client = input("Nowy adres obiektu: ")
            c.execute("UPDATE objects SET client = ? WHERE id = ?", (new_client, obj_id))

        elif choice == "3":
            print("1. Sprzątanie (stawka za jedno sprzątanie)")
            print("2. Ryczałt miesięczny")
            print("3. Jednorazowe mycie")
            t = input("Wybierz typ: ")

            if t == "1":
                new_rate = input_float("Stawka za jedno sprzątanie (PLN): ")
                c.execute("""
                    UPDATE objects 
                    SET billing_type = 'sprzatanie', monthly_rate = ?, ryczalt = NULL 
                    WHERE id = ?
                """, (new_rate, obj_id))

            elif t == "2":
                new_ryczalt = input_float("Kwota ryczałtu miesięcznego (PLN): ")
                c.execute("""
                    UPDATE objects 
                    SET billing_type = 'ryczalt', ryczalt = ?, monthly_rate = NULL 
                    WHERE id = ?
                """, (new_ryczalt, obj_id))

            elif t == "3":
                new_rate = input_float("Stawka za jednorazowe mycie (PLN): ")
                c.execute("""
                    UPDATE objects 
                    SET billing_type = 'jednorazowe', monthly_rate = ?, ryczalt = NULL 
                    WHERE id = ?
                """, (new_rate, obj_id))

            else:
                print("Nieprawidłowy wybór.")

        elif choice == "4":
            new_rate = input_float("Nowa stawka (PLN): ")
            c.execute("UPDATE objects SET monthly_rate = ?, ryczalt = NULL WHERE id = ?", (new_rate, obj_id))

        elif choice == "5":
            new_ryczalt = input_float("Nowy ryczałt miesięczny (PLN): ")
            c.execute("UPDATE objects SET ryczalt = ?, monthly_rate = NULL WHERE id = ?", (new_ryczalt, obj_id))

        elif choice == "6":
            print("1. Aktywny")
            print("2. Nieaktywny")
            s = input("Wybierz status: ")
            if s == "1":
                c.execute("UPDATE objects SET active = 1 WHERE id = ?", (obj_id,))
            elif s == "2":
                c.execute("UPDATE objects SET active = 0 WHERE id = ?", (obj_id,))
            else:
                print("Nieprawidłowy wybór.")

        elif choice == "0":
            break

        else:
            print("Nieprawidłowy wybór.")

        conn.commit()
        print("Zaktualizowano.\n")

    conn.close()
    print("Edycja obiektu zakończona.\n")


# --- EWIDENCJA GODZIN ---

def add_hours():
    conn = connect()
    c = conn.cursor()

    list_employees()
    emp_id = input_int("ID pracownika: ")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    date_str = input("Data (YYYY-MM-DD, puste = dziś): ").strip()
    if not date_str:
        date_str = datetime.datetime.today().strftime("%Y-%m-%d")

    hours = input_float("Liczba godzin: ")

    c.execute(
        "INSERT INTO hours (employee_id, object_id, date, hours) VALUES (?, ?, ?, ?)",
        (emp_id, obj_id, date_str, hours)
    )
    conn.commit()
    conn.close()
    print("Dodano wpis godzin.\n")

def add_cleaning_entry():
    print("\n--- Dodaj sprzątanie ---")

    # Wybór obiektu
    list_objects()
    obj_id = input_int("Podaj ID obiektu: ")

    # Data sprzątania
    date = input("Data sprzątania (YYYY-MM-DD): ").strip()

    conn = connect()
    c = conn.cursor()

    # Pobranie listy pracowników
    c.execute("SELECT id, name FROM employees WHERE active = 1 ORDER BY id")
    employees = c.fetchall()

    if not employees:
        print("Brak aktywnych pracowników.")
        conn.close()
        return

    print("\n--- Wybierz pracowników, którzy byli na sprzątaniu ---")
    print("Podawaj ID pracowników po kolei. 0 = koniec.")

    selected = []

    while True:
        emp_id = input_int("ID pracownika (0 = zakończ): ")
        if emp_id == 0:
            break

        # Sprawdzenie czy istnieje
        if not any(e[0] == emp_id for e in employees):
            print("Nie ma takiego pracownika.")
            continue

        hours = input_float(f"Ile godzin przepracował pracownik {emp_id}? ")
        selected.append((emp_id, hours))

    if not selected:
        print("Nie wybrano żadnych pracowników. Anulowano.\n")
        conn.close()
        return

    # Zapis godzin
    for emp_id, hours in selected:
        c.execute("""
            INSERT INTO hours (employee_id, object_id, date, hours)
            VALUES (?, ?, ?, ?)
        """, (emp_id, obj_id, date, hours))

    conn.commit()
    conn.close()

    print("\nSprzątanie zostało zapisane.")
    print(f"Liczba pracowników: {len(selected)}")
    print("Wpisy godzin dodane.\n")


def edit_hours():
    conn = connect()
    c = conn.cursor()

    print("\n--- Edytuj wpis godzin ---")

    # Pobranie listy wpisów
    c.execute("""
        SELECT h.id, h.date, e.name, o.name, h.hours, h.employee_id, h.object_id
        FROM hours h
        JOIN employees e ON h.employee_id = e.id
        JOIN objects o ON h.object_id = o.id
        ORDER BY h.date DESC, h.id DESC
    """)
    rows = c.fetchall()

    if not rows:
        print("Brak wpisów godzin do edycji.\n")
        conn.close()
        return

    # Wyświetlenie listy
    for r in rows:
        rec_id, date, emp_name, obj_name, hours, emp_id, obj_id = r
        print(f"{rec_id}: {date} | {emp_name} | {obj_name} | {hours} h")

    edit_id = input_int("\nPodaj ID wpisu do edycji (0 = anuluj): ")
    if edit_id == 0:
        print("Anulowano.\n")
        conn.close()
        return

    # Pobranie aktualnych danych
    c.execute("""
        SELECT employee_id, object_id, date, hours
        FROM hours
        WHERE id = ?
    """, (edit_id,))
    row = c.fetchone()

    if not row:
        print("Nie znaleziono wpisu.\n")
        conn.close()
        return

    current_emp, current_obj, current_date, current_hours = row

    print("\n--- Pola do edycji ---")
    print(f"1. Pracownik (obecnie ID: {current_emp})")
    print(f"2. Obiekt (obecnie ID: {current_obj})")
    print(f"3. Data (obecnie: {current_date})")
    print(f"4. Liczba godzin (obecnie: {current_hours})")
    print("0. Zakończ edycję")

    while True:
        ch = input("Wybierz pole do edycji: ")

        if ch == "1":
            list_employees()
            new_emp = input_int("Nowy ID pracownika: ")
            c.execute("UPDATE hours SET employee_id = ? WHERE id = ?", (new_emp, edit_id))

        elif ch == "2":
            list_objects()
            new_obj = input_int("Nowy ID obiektu: ")
            c.execute("UPDATE hours SET object_id = ? WHERE id = ?", (new_obj, edit_id))

        elif ch == "3":
            new_date = input("Nowa data (YYYY-MM-DD): ")
            c.execute("UPDATE hours SET date = ? WHERE id = ?", (new_date, edit_id))

        elif ch == "4":
            new_hours = input_float("Nowa liczba godzin: ")
            c.execute("UPDATE hours SET hours = ? WHERE id = ?", (new_hours, edit_id))

        elif ch == "0":
            break

        else:
            print("Nieprawidłowy wybór.")
            continue

        conn.commit()
        print("Zaktualizowano.\n")

    conn.close()
    print("Edycja wpisu godzin zakończona.\n")



def list_hours():
    conn = connect()
    c = conn.cursor()
    c.execute("""
    SELECT h.date, e.name, o.name, h.hours
    FROM hours h
    JOIN employees e ON h.employee_id = e.id
    JOIN objects o ON h.object_id = o.id
    ORDER BY h.date
    """)
    rows = c.fetchall()
    conn.close()

    print("\n--- Ewidencja godzin ---")
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]} h")
    print("------------------------\n")

def delete_hours():
    conn = connect()
    c = conn.cursor()

    print("\n--- Usuń wpis godzin ---")
    c.execute("""
        SELECT h.id, h.date, e.name, o.name, h.hours
        FROM hours h
        JOIN employees e ON h.employee_id = e.id
        JOIN objects o ON h.object_id = o.id
        ORDER BY h.date DESC, h.id DESC
    """)
    rows = c.fetchall()

    if not rows:
        print("Brak wpisów godzin.\n")
        conn.close()
        return

    for r in rows:
        rec_id, date, emp_name, obj_name, hours = r
        print(f"{rec_id}: {date} | {emp_name} | {obj_name} | {hours} h")

    del_id = input_int("Podaj ID wpisu do usunięcia (0 = anuluj): ")
    if del_id == 0:
        conn.close()
        print("Anulowano.\n")
        return

    c.execute("DELETE FROM hours WHERE id = ?", (del_id,))
    conn.commit()
    conn.close()
    print("Usunięto wpis godzin.\n")


# --- FAKTURY / CHECKLISTY ---

def add_checklist_item():
    print("\n--- Dodaj pozycję checklisty ---")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    item = input("Nazwa pozycji checklisty: ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        INSERT INTO checklist_templates (object_id, item_name)
        VALUES (?, ?)
    """, (obj_id, item))

    conn.commit()
    conn.close()
    print("Dodano pozycję checklisty.\n")

def list_checklist_items():
    print("\n--- Lista checklisty obiektu ---")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT id, item_name
        FROM checklist_templates
        WHERE object_id = ?
        ORDER BY id
    """, (obj_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak checklisty dla tego obiektu.\n")
        return

    for r in rows:
        print(f"{r[0]}: {r[1]}")

    print("-------------------------\n")

def complete_checklist_item():
    print("\n--- Wykonanie checklisty ---")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    list_employees()
    emp_id = input_int("ID pracownika wykonującego: ")

    conn = connect()
    c = conn.cursor()

    # Pobierz checklistę
    c.execute("""
        SELECT item_name
        FROM checklist_templates
        WHERE object_id = ?
    """, (obj_id,))
    items = c.fetchall()

    if not items:
        print("Brak checklisty dla tego obiektu.\n")
        conn.close()
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    print("\n--- Odhaczanie checklisty ---")
    for (item_name,) in items:
        done = yes_no(f"Czy wykonano: {item_name}?")
        status = "DONE" if done else "NOT_DONE"

        c.execute("""
            INSERT INTO checklist_results (object_id, employee_id, date, item_name, status)
            VALUES (?, ?, ?, ?, ?)
        """, (obj_id, emp_id, today, item_name, status))

    conn.commit()
    conn.close()
    print("Checklistę zapisano.\n")

def raport_checklist():
    print("\n--- Raport checklist ---")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT date, item_name, status, e.name
        FROM checklist_results cr
        JOIN employees e ON cr.employee_id = e.id
        WHERE cr.object_id = ?
          AND strftime('%Y-%m', cr.date) = ?
        ORDER BY cr.date
    """, (obj_id, f"{year}-{month:02d}"))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak checklist w tym miesiącu.\n")
        return

    print(f"\n=== RAPORT CHECKLIST {year}-{month:02d} ===\n")

    for date, item, status, emp in rows:
        print(f"{date} | {emp} | {item} | {status}")

    print("\n=== KONIEC RAPORTU ===\n")


def update_invoice_status():
    conn = connect()
    c = conn.cursor()

    list_objects()
    obj_id = input_int("ID obiektu: ")
    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    invoice_sent = 1 if yes_no("Faktura wysłana?") else 0
    invoice_paid = 1 if yes_no("Faktura zapłacona?") else 0
    checklist_done = 1 if yes_no("Checklisty zrobione?") else 0

    c.execute("""
    SELECT id FROM invoices
    WHERE object_id = ? AND year = ? AND month = ?
    """, (obj_id, year, month))
    row = c.fetchone()

    if row:
        c.execute("""
        UPDATE invoices
        SET invoice_sent = ?, invoice_paid = ?, checklist_done = ?
        WHERE id = ?
        """, (invoice_sent, invoice_paid, checklist_done, row[0]))
        print("Zaktualizowano status faktury/checklisty.\n")
    else:
        c.execute("""
        INSERT INTO invoices (object_id, year, month, invoice_sent, invoice_paid, checklist_done)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (obj_id, year, month, invoice_sent, invoice_paid, checklist_done))
        print("Dodano status faktury/checklisty.\n")

    conn.commit()
    conn.close()


# --- RAPORTY ---

def calc_month_report(year, month):
    conn = connect()
    c = conn.cursor()

    # Pobieramy obiekty
    c.execute("""
        SELECT id, name, billing_type, monthly_rate, ryczalt
        FROM objects
        WHERE active = 1
    """)
    objects = c.fetchall()

    # Pobieramy statusy faktur
    c.execute("""
        SELECT object_id, invoice_sent, invoice_paid, checklist_done
        FROM invoices
        WHERE year = ? AND month = ?
    """, (year, month))
    inv_rows = c.fetchall()
    inv_map = {r[0]: (r[1], r[2], r[3]) for r in inv_rows}

    report = []
    total_revenue = 0.0
    total_cost = 0.0

    for obj in objects:
        obj_id, name, billing_type, rate, ryczalt = obj

        # Liczymy godziny i koszt pracowników
        c.execute("""
            SELECT SUM(h.hours), SUM(h.hours * e.hourly_rate)
            FROM hours h
            JOIN employees e ON h.employee_id = e.id
            WHERE h.object_id = ?
              AND strftime('%Y-%m', h.date) = ?
        """, (obj_id, f"{year}-{month:02d}"))

        hours_sum, cost_sum = c.fetchone()
        hours_sum = hours_sum or 0
        cost_sum = cost_sum or 0

        # Liczymy liczbę sprzątań (dni z wpisami)
        c.execute("""
            SELECT COUNT(DISTINCT date)
            FROM hours
            WHERE object_id = ?
              AND strftime('%Y-%m', date) = ?
        """, (obj_id, f"{year}-{month:02d}"))
        cleanings = c.fetchone()[0] or 0

        # --- PRZYCHÓD ---
        if billing_type == "sprzatanie":
            revenue = cleanings * (rate or 0)

        elif billing_type == "ryczalt":
            revenue = ryczalt or 0

        elif billing_type == "jednorazowe":
            # tylko jeśli były godziny
            revenue = (rate or 0) if cleanings > 0 else 0

        else:
            revenue = 0

        margin = revenue - cost_sum
        margin_pct = (margin / revenue * 100) if revenue > 0 else 0

        # Statusy faktur
        inv = inv_map.get(obj_id, (0, 0, 0))
        invoice_sent = bool(inv[0])
        invoice_paid = bool(inv[1])
        checklist_done = bool(inv[2])

        report.append({
            "object_id": obj_id,
            "object": name,
            "billing_type": billing_type,
            "cleanings": cleanings,
            "hours": hours_sum,
            "revenue": revenue,
            "cost": cost_sum,
            "margin": margin,
            "margin_pct": margin_pct,
            "invoice_sent": invoice_sent,
            "invoice_paid": invoice_paid,
            "checklist_done": checklist_done
        })

        total_revenue += revenue
        total_cost += cost_sum

    conn.close()

    total_margin = total_revenue - total_cost
    total_margin_pct = (total_margin / total_revenue * 100) if total_revenue > 0 else 0

    return report, total_revenue, total_cost, total_margin, total_margin_pct



def show_month_report():
    month = input("Podaj miesiąc (MM): ")
    year = input("Podaj rok (YYYY): ")

    conn = connect()
    c = conn.cursor()

    print(f"\n=== RAPORT MIESIĘCZNY {month}/{year} ===\n")

    # --- PRZYCHODY Z OBIEKTÓW ---
    print(">>> PRZYCHODY <<<\n")

    c.execute("""
        SELECT id, name, billing_type, monthly_rate, ryczalt, invoice_sent, invoice_paid
        FROM objects
        WHERE active = 1
    """)
    objects = c.fetchall()

    total_income = 0

    for obj in objects:
        obj_id, name, billing_type, monthly_rate, ryczalt, sent, paid = obj

        print(f"\nObiekt: {name}")
        print(f"Typ rozliczenia: {billing_type}")

        if billing_type == "godzinowy":
            # policz godziny
            c.execute("""
                SELECT SUM(hours)
                FROM hours
                WHERE object_id = ?
                  AND strftime('%m', date) = ?
                  AND strftime('%Y', date) = ?
            """, (obj_id, month, year))
            total_hours = c.fetchone()[0] or 0

            income = total_hours * (monthly_rate or 0)
            print(f"Godziny: {total_hours}")
            print(f"Stawka: {monthly_rate} PLN/h")
            print(f"Przychód: {income} PLN")

        else:  # ryczałt
            income = ryczalt or 0
            print(f"Ryczałt miesięczny: {income} PLN")

        print(f"Faktura wysłana: {'TAK' if sent else 'NIE'}")
        print(f"Faktura opłacona: {'TAK' if paid else 'NIE'}")

        total_income += income

    print(f"\nSUMA PRZYCHODÓW: {total_income} PLN\n")

    # --- KOSZTY PRACOWNIKÓW ---
    print("\n>>> KOSZTY PRACOWNIKÓW <<<\n")

    c.execute("SELECT id, name, hourly_rate, monthly_salary FROM employees WHERE active = 1")
    employees = c.fetchall()

    total_employee_cost = 0

    for emp in employees:
        emp_id, name, hourly_rate, monthly_salary = emp

        print(f"\nPracownik: {name}")

        if monthly_salary:
            print(f"Etat: {monthly_salary} PLN")
            total_employee_cost += monthly_salary
        else:
            # policz godziny
            c.execute("""
                SELECT SUM(hours)
                FROM hours
                WHERE employee_id = ?
                  AND strftime('%m', date) = ?
                  AND strftime('%Y', date) = ?
            """, (emp_id, month, year))
            hours_sum = c.fetchone()[0] or 0

            cost = hours_sum * hourly_rate
            print(f"Godziny: {hours_sum}")
            print(f"Stawka: {hourly_rate} PLN/h")
            print(f"Koszt: {cost} PLN")

            total_employee_cost += cost

    print(f"\nSUMA KOSZTÓW PRACOWNIKÓW: {total_employee_cost} PLN\n")



    # --- KOSZTY DODATKOWE ---
    print("\n>>> KOSZTY DODATKOWE <<<\n")

    c.execute("""
        SELECT category, description, amount, date
        FROM other_costs
        WHERE strftime('%m', date) = ?
          AND strftime('%Y', date) = ?
    """, (month, year))

    other_costs = c.fetchall()
    total_other_costs = sum(x[2] for x in other_costs)

    for cat, desc, amount, date in other_costs:
        print(f"{date} | {cat} | {desc} | {amount} PLN")

    print(f"\nSUMA KOSZTÓW DODATKOWYCH: {total_other_costs} PLN\n")

    # --- MARŻA ---
    margin = total_income - total_employee_cost - total_other_costs

    print("\n>>> PODSUMOWANIE <<<\n")
    print(f"Przychody: {total_income} PLN")
    print(f"Koszty pracowników: {total_employee_cost} PLN")
    print(f"Koszty dodatkowe: {total_other_costs} PLN")
    print(f"MARŻA: {margin} PLN")

    conn.close()
    print("\n=== KONIEC RAPORTU ===\n")



def show_year_report():
    year = input_int("Rok (YYYY): ")

    total_rev_year = 0.0
    total_cost_year = 0.0
    total_margin_year = 0.0

    print(f"\n=== RAPORT ROCZNY {year} ===")
    for month in range(1, 13):
        _, total_rev, total_cost, total_margin, total_margin_pct = calc_month_report(year, month)
        total_rev_year += total_rev
        total_cost_year += total_cost
        total_margin_year += total_margin
        print(f"{year}-{month:02d}: przychód {total_rev:.2f} PLN, "
              f"koszt {total_cost:.2f} PLN, marża {total_margin:.2f} PLN ({total_margin_pct:.1f}%)")

    total_margin_pct_year = (total_margin_year / total_rev_year * 100) if total_rev_year > 0 else 0.0
    print("\n=== PODSUMOWANIE ROCZNE ===")
    print(f"Łączny przychód: {total_rev_year:.2f} PLN")
    print(f"Łączny koszt:    {total_cost_year:.2f} PLN")
    print(f"Łączna marża:    {total_margin_year:.2f} PLN ({total_margin_pct_year:.1f}%)")
    print("===========================\n")
# --- KALKULATOR MARŻY ---

def margin_calculator():
    print("\n--- Kalkulator marży dla nowego zlecenia ---")
    revenue = input_float("Przychód miesięczny (PLN): ")
    total_hours = input_float("Łączna liczba godzin w miesiącu: ")
    avg_rate = input_float("Średnia stawka godzinowa pracownika (PLN): ")
    cost = total_hours * avg_rate
    margin = revenue - cost
    margin_pct = (margin / revenue * 100) if revenue > 0 else 0.0
    print(f"Koszt: {cost:.2f} PLN")
    print(f"Marża: {margin:.2f} PLN ({margin_pct:.1f}%)\n")

# --- PDF ---

def export_month_report_pdf():
    year = input_int("Rok (YYYY): ")
    month = input_int("Miesiąc (1-12): ")

    report, total_rev, total_cost, total_margin, total_margin_pct = calc_month_report(year, month)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Raport miesieczny {year}-{month:02d}", ln=True)

    pdf.set_font("Arial", "", 10)
    pdf.ln(5)

    for r in report:
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 6, f"Obiekt: {r['object']}", ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 5, f"Przychod: {r['revenue']:.2f} PLN", ln=True)
        pdf.cell(0, 5, f"Koszt: {r['cost']:.2f} PLN", ln=True)
        pdf.cell(0, 5, f"Marza: {r['margin']:.2f} PLN ({r['margin_pct']:.1f}%)", ln=True)
        pdf.cell(0, 5, f"Sprzatania w miesiacu: {r['cleanings_count']}", ln=True)
        pdf.cell(0, 5, f"Faktura wyslana: {r['invoice_sent']}", ln=True)
        pdf.cell(0, 5, f"Faktura zaplacona: {r['invoice_paid']}", ln=True)
        pdf.cell(0, 5, f"Checklisty: {r['checklist_done']}", ln=True)
        pdf.ln(3)

    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 6, "Podsumowanie:", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, f"Laczny przychod: {total_rev:.2f} PLN", ln=True)
    pdf.cell(0, 5, f"Laczny koszt: {total_cost:.2f} PLN", ln=True)
    pdf.cell(0, 5, f"Laczna marza: {total_margin:.2f} PLN ({total_margin_pct:.1f}%)", ln=True)

    filename = f"raport_{year}_{month:02d}.pdf"
    pdf.output(filename)
    print(f"Zapisano PDF: {filename}\n")

def delete_employee():
    list_employees()
    emp_id = input_int("Podaj ID pracownika do usunięcia: ")

    conn = connect()
    c = conn.cursor()

    c.execute("SELECT id FROM employees WHERE id = ?", (emp_id,))
    if not c.fetchone():
        print("Nie znaleziono pracownika.\n")
        conn.close()
        return

    c.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    print("Usunięto pracownika.\n")

def delete_object():
    list_objects()
    obj_id = input_int("Podaj ID obiektu do usunięcia: ")

    conn = connect()
    c = conn.cursor()

    c.execute("SELECT id FROM objects WHERE id = ?", (obj_id,))
    if not c.fetchone():
        print("Nie znaleziono obiektu.\n")
        conn.close()
        return

    c.execute("DELETE FROM objects WHERE id = ?", (obj_id,))
    conn.commit()
    conn.close()
    print("Usunięto obiekt.\n")

def add_other_cost():
    list_objects()
    obj_id = input_int("ID obiektu (0 = koszt ogólny): ")

    date_str = input("Data (YYYY-MM-DD, puste = dziś): ").strip()
    if not date_str:
        date_str = datetime.datetime.today().strftime("%Y-%m-%d")

    category = input("Kategoria (chemia/paliwo/maszyny/inne): ")
    description = input("Opis: ")
    amount = input_float("Kwota (PLN): ")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        INSERT INTO other_costs (object_id, date, category, description, amount)
        VALUES (?, ?, ?, ?, ?)
    """, (obj_id if obj_id != 0 else None, date_str, category, description, amount))

    conn.commit()
    conn.close()
    print("Dodano koszt dodatkowy.\n")

def set_employee_day_status():
    list_employees()
    emp_id = input_int("Podaj ID pracownika: ")

    date_from = input("Data od (YYYY-MM-DD): ")
    date_to = input("Data do (YYYY-MM-DD): ")

    print("1. PRACA")
    print("2. URLOP")
    print("3. L4")
    choice = input("Wybierz status: ")

    status = {"1": "PRACA", "2": "URLOP", "3": "L4"}.get(choice)
    if not status:
        print("Nieprawidłowa opcja.")
        return

    try:
        d_from = datetime.datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        print("Błędny format daty.")
        return

    if d_to < d_from:
        print("Data 'do' nie może być wcześniejsza niż 'od'.")
        return

    conn = connect()
    c = conn.cursor()

    current = d_from
    while current <= d_to:
        c.execute("DELETE FROM employee_days WHERE employee_id = ? AND date = ?", (emp_id, current.isoformat()))
        c.execute(
            "INSERT INTO employee_days (employee_id, date, status) VALUES (?, ?, ?)",
            (emp_id, current.isoformat(), status)
        )
        current += datetime.timedelta(days=1)

    conn.commit()
    conn.close()
    print("Status dni zapisany dla wybranego zakresu.\n")

##taski##    

def add_task():
    conn = connect()
    c = conn.cursor()

    print("\n--- Dodaj zadanie ---")
    list_objects()
    obj_id = input_int("ID obiektu (0 = brak): ")

    list_employees()
    emp_id = input_int("ID pracownika (0 = nieprzypisane): ")

    title = input("Tytuł zadania: ")
    description = input("Opis zadania: ")
    priority = input("Priorytet (niski/normalny/wysoki): ")
    deadline = input("Termin (YYYY-MM-DD, puste = brak): ").strip()
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if obj_id == 0:
        obj_id = None
    if emp_id == 0:
        emp_id = None
    if not deadline:
        deadline = None

    c.execute("""
        INSERT INTO tasks (object_id, employee_id, title, description, priority, deadline, status, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, NULL)
    """, (obj_id, emp_id, title, description, priority, deadline, created_at))

    conn.commit()
    conn.close()
    print("Dodano zadanie.\n")

def list_tasks():
    conn = connect()
    c = conn.cursor()

    print("\n--- Lista zadań ---")
    c.execute("""
        SELECT t.id, o.name, e.name, t.title, t.priority, t.deadline, t.status
        FROM tasks t
        LEFT JOIN objects o ON t.object_id = o.id
        LEFT JOIN employees e ON t.employee_id = e.id
        ORDER BY t.status, t.deadline IS NULL, t.deadline, t.id
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak zadań.\n")
        return

    for r in rows:
        task_id, obj_name, emp_name, title, priority, deadline, status = r
        obj_info = obj_name if obj_name else "Brak obiektu"
        emp_info = emp_name if emp_name else "Nieprzypisane"
        deadline_info = deadline if deadline else "brak terminu"
        print(f"{task_id}: [{status}] {title} | obiekt: {obj_info} | pracownik: {emp_info} | priorytet: {priority} | termin: {deadline_info}")
    print("--------------------\n")

def edit_task():
    list_tasks()
    task_id = input_int("Podaj ID zadania do edycji (0 = anuluj): ")
    if task_id == 0:
        print("Anulowano.\n")
        return

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT object_id, employee_id, title, description, priority, deadline, status
        FROM tasks
        WHERE id = ?
    """, (task_id,))
    row = c.fetchone()

    if not row:
        print("Nie znaleziono zadania.\n")
        conn.close()
        return

    current_obj, current_emp, current_title, current_desc, current_prio, current_deadline, current_status = row

    print("\n--- Edycja zadania ---")
    print(f"1. Obiekt (obecnie: {current_obj})")
    print(f"2. Pracownik (obecnie: {current_emp})")
    print(f"3. Tytuł (obecnie: {current_title})")
    print(f"4. Opis (obecnie: {current_desc})")
    print(f"5. Priorytet (obecnie: {current_prio})")
    print(f"6. Termin (obecnie: {current_deadline})")
    print(f"7. Status (obecnie: {current_status})")
    print("0. Zakończ edycję")

    while True:
        ch = input("Wybierz pole do edycji: ")

        if ch == "1":
            list_objects()
            new_obj = input_int("Nowy ID obiektu (0 = brak): ")
            new_obj = None if new_obj == 0 else new_obj
            c.execute("UPDATE tasks SET object_id = ? WHERE id = ?", (new_obj, task_id))

        elif ch == "2":
            list_employees()
            new_emp = input_int("Nowy ID pracownika (0 = nieprzypisane): ")
            new_emp = None if new_emp == 0 else new_emp
            c.execute("UPDATE tasks SET employee_id = ? WHERE id = ?", (new_emp, task_id))

        elif ch == "3":
            new_title = input("Nowy tytuł: ")
            c.execute("UPDATE tasks SET title = ? WHERE id = ?", (new_title, task_id))

        elif ch == "4":
            new_desc = input("Nowy opis: ")
            c.execute("UPDATE tasks SET description = ? WHERE id = ?", (new_desc, task_id))

        elif ch == "5":
            new_prio = input("Nowy priorytet (niski/normalny/wysoki): ")
            c.execute("UPDATE tasks SET priority = ? WHERE id = ?", (new_prio, task_id))

        elif ch == "6":
            new_deadline = input("Nowy termin (YYYY-MM-DD, puste = brak): ").strip()
            if not new_deadline:
                new_deadline = None
            c.execute("UPDATE tasks SET deadline = ? WHERE id = ?", (new_deadline, task_id))

        elif ch == "7":
            print("Statusy: OPEN / IN_PROGRESS / DONE / CANCELED")
            new_status = input("Nowy status: ").strip().upper()
            c.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))

        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.")
            continue

        conn.commit()
        print("Zaktualizowano.\n")

    conn.close()
    print("Edycja zadania zakończona.\n")

def complete_task():
    list_tasks()
    task_id = input_int("Podaj ID zadania do oznaczenia jako wykonane (0 = anuluj): ")
    if task_id == 0:
        print("Anulowano.\n")
        return

    conn = connect()
    c = conn.cursor()

    completed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        UPDATE tasks
        SET status = 'DONE', completed_at = ?
        WHERE id = ?
    """, (completed_at, task_id))

    conn.commit()
    conn.close()
    print("Zadanie oznaczone jako wykonane.\n")

def tasks_menu():
    while True:
        print("\n--- ZADANIA ---")
        print("1. Dodaj zadanie")
        print("2. Lista zadań")
        print("3. Edytuj zadanie")
        print("4. Oznacz zadanie jako wykonane")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_task()
        elif ch == "2":
            list_tasks()
        elif ch == "3":
            edit_task()
        elif ch == "4":
            complete_task()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

##Usterki##

def add_issue():
    print("\n--- Zgłoś usterkę ---")

    list_objects()
    obj_id = input_int("ID obiektu: ")

    list_employees()
    emp_id = input_int("ID pracownika zgłaszającego: ")

    description = input("Opis usterki: ")
    photo_path = input("Ścieżka do zdjęcia (opcjonalnie, ENTER = brak): ").strip()
    if photo_path == "":
        photo_path = None

    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        INSERT INTO issues (object_id, employee_id, description, photo_path, status, created_at, resolved_at)
        VALUES (?, ?, ?, ?, 'OPEN', ?, NULL)
    """, (obj_id, emp_id, description, photo_path, created_at))

    conn.commit()
    conn.close()

    print("Usterka została zgłoszona.\n")

def list_issues():
    print("\n--- Lista usterek ---")

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT i.id, o.name, e.name, i.description, i.status, i.created_at, i.resolved_at
        FROM issues i
        JOIN objects o ON i.object_id = o.id
        JOIN employees e ON i.employee_id = e.id
        ORDER BY i.status, i.created_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak zgłoszonych usterek.\n")
        return

    for r in rows:
        issue_id, obj_name, emp_name, desc, status, created, resolved = r
        resolved_info = resolved if resolved else "NIEZAMKNIĘTA"
        print(f"{issue_id}: [{status}] Obiekt: {obj_name} | Zgłosił: {emp_name}")
        print(f"    Opis: {desc}")
        print(f"    Utworzono: {created} | Zakończono: {resolved_info}")
        print()

    print("-------------------------\n")

def resolve_issue():
    print("\n--- Zamknij usterkę ---")

    list_issues()
    issue_id = input_int("Podaj ID usterki do zamknięcia (0 = anuluj): ")

    if issue_id == 0:
        print("Anulowano.\n")
        return

    conn = connect()
    c = conn.cursor()

    # Sprawdź, czy istnieje
    c.execute("SELECT status FROM issues WHERE id = ?", (issue_id,))
    row = c.fetchone()

    if not row:
        print("Nie znaleziono usterki.\n")
        conn.close()
        return

    if row[0] == "CLOSED":
        print("Ta usterka jest już zamknięta.\n")
        conn.close()
        return

    resolved_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        UPDATE issues
        SET status = 'CLOSED', resolved_at = ?
        WHERE id = ?
    """, (resolved_at, issue_id))

    conn.commit()
    conn.close()

    print("Usterka została zamknięta.\n")



##menu obecnosci##

def attendance_menu():
    while True:
        print("\n--- OBECNOŚĆ PRACOWNIKÓW ---")
        print("1. Rozpocznij pracę")
        print("2. Zakończ pracę")
        print("3. Lista obecności")
        print("4. Raport obecności")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            start_attendance()
        elif ch == "2":
            end_attendance()
        elif ch == "3":
            list_attendance()
        elif ch == "4":
            raport_obecnosci()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

##menu checklist##

def checklist_menu():
    while True:
        print("\n--- CHECKLISTY ---")
        print("1. Dodaj pozycję checklisty")
        print("2. Wyświetl checklistę obiektu")
        print("3. Wykonaj checklistę")
        print("4. Raport checklist")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_checklist_item()
        elif ch == "2":
            list_checklist_items()
        elif ch == "3":
            complete_checklist_item()
        elif ch == "4":
            raport_checklist()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

#menu usterek#

def issues_menu():
    while True:
        print("\n--- USTERKI ---")
        print("1. Zgłoś usterkę")
        print("2. Lista usterek")
        print("3. Zamknij usterkę")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_issue()
        elif ch == "2":
            list_issues()
        elif ch == "3":
            resolve_issue()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

            




# --- MENU ---

def main():
    init_db()
    daily_backup()

    while True:
        print("=== LŚNIĄCA STREFA - PANEL TEKSTOWY ===")
        print("1. Pracownicy")
        print("2. Obiekty / Zlecenia")
        print("3. Godziny pracy")
        print("4. Koszty dodatkowe")
        print("5. Raporty")
        print("6. Narzędzia")
        print("7. Zadania")
        print("8. Obecność pracowników")
        print("9. Checklisty")
        print("10. Usterki")
        print("11. Raporty rozszerzone")
        print("0. Wyjście")

        choice = input("Wybierz opcję: ").strip()

        if choice == "1":
            employees_menu()
        elif choice == "2":
            objects_menu()
        elif choice == "3":
            hours_menu()
        elif choice == "4":
            costs_menu()
        elif choice == "5":
            reports_menu()
        elif choice == "6":
            tools_menu()
        elif choice == "7":
            tasks_menu()
        elif choice == "8":
            attendance_menu()
        elif choice == "9":
            checklist_menu()
        elif choice == "10":
            issues_menu()
        elif choice == "11":
            extended_reports_menu()    
        elif choice == "0":
            print("Do zobaczenia.")
            break
        else:
            print("Nieprawidłowy wybór.\n")

def employees_menu():
    while True:
        print("\n--- PRACOWNICY ---")
        print("1. Dodaj pracownika")
        print("2. Lista pracowników")
        print("3. Edytuj pracownika")
        print("4. Usuń pracownika")
        print("5. Ustaw status dnia (PRACA/URLOP/L4)")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_employee()
        elif ch == "2":
            list_employees()
        elif ch == "3":
            edit_employee()
        elif ch == "4":
            delete_employee()
        elif ch == "5":
            set_employee_day_status()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

def objects_menu():
    while True:
        print("\n--- OBIEKTY / ZLECENIA ---")
        print("1. Dodaj obiekt")
        print("2. Lista obiektów")
        print("3. Edytuj obiekt")
        print("4. Usuń obiekt")
        print("5. Ustaw status faktury/checklisty")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_object()
        elif ch == "2":
            list_objects()
        elif ch == "3":
            edit_object()
        elif ch == "4":
            delete_object()
        elif ch == "5":
            update_invoice_status()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

def hours_menu():
    while True:
        print("\n--- GODZINY PRACY / SPRZĄTANIA ---")
        print("1. Dodaj wpis godzin (ręcznie)")
        print("2. Dodaj sprzątanie (lista pracowników + godziny)")
        print("3. Lista godzin")
        print("4. Usuń wpis godzin")
        print("5. Edytuj wpis godzin")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_hours()
        elif ch == "2":
            add_cleaning_entry()
        elif ch == "3":
            list_hours()
        elif ch == "4":
            delete_hours()
        elif ch == "5":
            edit_hours()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")



def list_other_costs():
    conn = connect()
    c = conn.cursor()

    print("\n--- Lista kosztów dodatkowych ---")

    c.execute("""
        SELECT id, object_id, date, category, description, amount
        FROM other_costs
        ORDER BY date DESC, id DESC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Brak kosztów dodatkowych.\n")
        return

    for r in rows:
        cost_id, obj_id, date, category, description, amount = r
        obj_info = f"Obiekt ID {obj_id}" if obj_id else "Koszt ogólny"
        print(f"{cost_id}: {date} | {obj_info} | {category} | {description} | {amount} PLN")

    print("-------------------------------\n")

def delete_other_cost():
    conn = connect()
    c = conn.cursor()

    print("\n--- Usuń koszt dodatkowy ---")

    c.execute("""
        SELECT id, object_id, date, category, description, amount
        FROM other_costs
        ORDER BY date DESC, id DESC
    """)
    rows = c.fetchall()

    if not rows:
        print("Brak kosztów do usunięcia.\n")
        conn.close()
        return

    # Wyświetlanie listy kosztów
    for r in rows:
        cost_id, obj_id, date, category, description, amount = r
        obj_info = f"Obiekt ID {obj_id}" if obj_id else "Koszt ogólny"
        print(f"{cost_id}: {date} | {obj_info} | {category} | {description} | {amount} PLN")

    del_id = input_int("\nPodaj ID kosztu do usunięcia (0 = anuluj): ")

    if del_id == 0:
        print("Anulowano.\n")
        conn.close()
        return

    # Sprawdzenie czy istnieje
    c.execute("SELECT id FROM other_costs WHERE id = ?", (del_id,))
    if not c.fetchone():
        print("Nie znaleziono kosztu o takim ID.\n")
        conn.close()
        return

    # Usuwanie
    c.execute("DELETE FROM other_costs WHERE id = ?", (del_id,))
    conn.commit()
    conn.close()

    print("Usunięto koszt dodatkowy.\n")


def edit_other_cost():
    conn = connect()
    c = conn.cursor()

    print("\n--- Edytuj koszt dodatkowy ---")

    # Pobranie listy kosztów
    c.execute("""
        SELECT id, object_id, date, category, description, amount
        FROM other_costs
        ORDER BY date DESC, id DESC
    """)
    rows = c.fetchall()

    if not rows:
        print("Brak kosztów do edycji.\n")
        conn.close()
        return

    # Wyświetlenie listy
    for r in rows:
        cost_id, obj_id, date, category, description, amount = r
        obj_info = f"Obiekt ID {obj_id}" if obj_id else "Koszt ogólny"
        print(f"{cost_id}: {date} | {obj_info} | {category} | {description} | {amount} PLN")

    cost_id = input_int("\nPodaj ID kosztu do edycji (0 = anuluj): ")
    if cost_id == 0:
        print("Anulowano.\n")
        conn.close()
        return

    # Pobranie aktualnych danych
    c.execute("""
        SELECT object_id, date, category, description, amount
        FROM other_costs
        WHERE id = ?
    """, (cost_id,))
    row = c.fetchone()

    if not row:
        print("Nie znaleziono kosztu.\n")
        conn.close()
        return

    current_obj, current_date, current_cat, current_desc, current_amount = row

    print("\n--- Pola do edycji ---")
    print(f"1. Obiekt (obecnie: {current_obj})")
    print(f"2. Data (obecnie: {current_date})")
    print(f"3. Kategoria (obecnie: {current_cat})")
    print(f"4. Opis (obecnie: {current_desc})")
    print(f"5. Kwota (obecnie: {current_amount} PLN)")
    print("0. Zakończ edycję")

    while True:
        ch = input("Wybierz pole do edycji: ")

        if ch == "1":
            list_objects()
            new_obj = input_int("Nowy ID obiektu (0 = koszt ogólny): ")
            new_obj = None if new_obj == 0 else new_obj
            c.execute("UPDATE other_costs SET object_id = ? WHERE id = ?", (new_obj, cost_id))

        elif ch == "2":
            new_date = input("Nowa data (YYYY-MM-DD): ")
            c.execute("UPDATE other_costs SET date = ? WHERE id = ?", (new_date, cost_id))

        elif ch == "3":
            new_cat = input("Nowa kategoria: ")
            c.execute("UPDATE other_costs SET category = ? WHERE id = ?", (new_cat, cost_id))

        elif ch == "4":
            new_desc = input("Nowy opis: ")
            c.execute("UPDATE other_costs SET description = ? WHERE id = ?", (new_desc, cost_id))

        elif ch == "5":
            new_amount = input_float("Nowa kwota (PLN): ")
            c.execute("UPDATE other_costs SET amount = ? WHERE id = ?", (new_amount, cost_id))

        elif ch == "0":
            break

        else:
            print("Nieprawidłowy wybór.")
            continue

        conn.commit()
        print("Zaktualizowano.\n")

    conn.close()
    print("Edycja zakończona.\n")
    



def costs_menu():
    while True:
        print("\n--- KOSZTY DODATKOWE ---")
        print("1. Dodaj koszt dodatkowy")
        print("2. Lista kosztów")
        print("3. Usuń koszt dodatkowy")
        print("4. Edytuj koszt dodatkowy")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            add_other_cost()
        elif ch == "2":
            list_other_costs()
        elif ch == "3":
            delete_other_cost()
        elif ch == "4":
            edit_other_cost()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

def extended_reports_menu():
    while True:
        print("\n--- RAPORTY ROZSZERZONE ---")
        print("1. Raport zadań")
        print("2. Raport usterek")
        print("3. Raport checklist (rozszerzony)")
        print("4. Raport rentowności obiektów")
        print("5. Dashboard menedżerski")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            raport_tasks()
        elif ch == "2":
            raport_issues()
        elif ch == "3":
            raport_checklist_extended()
        elif ch == "4":
            raport_rentownosci()
        elif ch == "5":
            dashboard()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")
            



def reports_menu():
    while True:
        print("\n--- RAPORTY ---")
        print("1. Raport miesięczny (obiekty + koszty + marża)")
        print("2. Raport miesięczny pracowników")
        print("3. Raport roczny")
        print("4. Eksport raportu miesięcznego do PDF")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            show_month_report()
        elif ch == "2":
            raport_pracownicy()
        elif ch == "3":
            show_year_report()
        elif ch == "4":
            export_month_report_pdf()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")

def tools_menu():
    while True:
        print("\n--- NARZĘDZIA ---")
        print("1. Kalkulator marży")
        print("0. Powrót")

        ch = input("Wybierz opcję: ")

        if ch == "1":
            margin_calculator()
        elif ch == "0":
            break
        else:
            print("Nieprawidłowy wybór.\n")




# --- START PROGRAMU ---

if __name__ == "__main__":
    main()
