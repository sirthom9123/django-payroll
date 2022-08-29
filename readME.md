### Payroll System with Django

A payroll system developed on Django admin portal

Command To Execute on Windows:
python manage.py runserver

## Installation

Run `python -m venv venv` to create a virtual environment for the project

Run `venv/Scripts/activate` to activate the virtual environment

Run `pip install -r requirements.txt` to install the dependencies

## Run

### Command to migrate database

Run `python manage.py makemigrations` to make new migrations to db
Run `python manage.py migrate` to migrate to db

### Command to create a superuser

Run `python manage.py createsuperuser`

### Command to migrate database

Remember to collectstatic files for prod
Run `python manage.py collectstatic`

## Database

You can use any database of your choice.

## Access Admin

Add `http://127.0.0.1:8000/admin` to the URL in the address bar
