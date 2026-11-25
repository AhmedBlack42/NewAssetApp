from app.core.database import Database
from app.gui.main_window import MainWindow


def create_application(config):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    database = Database(config.database_path)
    database.initialize()
    return MainWindow(config, database)
