print("Старт программы")

from database.repository import create_database

print("Импорт выполнен")

if __name__ == "__main__":
    print("Создаем БД...")
    create_database()
    print("Готово!")