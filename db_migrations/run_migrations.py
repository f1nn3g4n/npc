# go through each python file in /migrations and run up() function
# if the file has not been run before, add it to the migrations table
# if the file has been run before, skip it
# if the file has been run before but the hash has changed, raise an error
# if the file has not been run before but the hash has changed, raise an error
# if there are any errors, rollback all migrations
# if all migrations run successfully, commit all migrations

import os
import sys
import hashlib
import importlib.util

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)
    print(f"Added {parent_dir} to sys.path")

from commands import create_oracle_connection

def get_migration_files():
    migration_files = []
    for file in os.listdir('migrations'):
        if file.endswith('.py'):
            migration_files.append(file)
    return migration_files

def get_migration_hash(file):
    with open(f'migrations/{file}', 'r') as f:
        file_contents = f.read()
        return hashlib.md5(file_contents.encode()).hexdigest()
    
def get_migration_status(file):
    connection = create_oracle_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM migrations WHERE filename = :filename", {'filename': file})
    result = cursor.fetchone()
    cursor.close()
    return result

def run_migration(file):
    spec = importlib.util.spec_from_file_location(file, f'migrations/{file}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.up()

def add_migration_to_table(file, hash):
    connection = create_oracle_connection()
    cursor = connection.cursor()
    cursor.execute("INSERT INTO migrations (filename, hash) VALUES (:filename, :hash)", {'filename': file, 'hash': hash})
    connection.commit()
    cursor.close()

def main():
    # Ensure current directory is db_migrations
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)

    # check if migrations table exists, create if not
    print('Checking if migrations table exists...', flush=True)
    connection = create_oracle_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT table_name FROM user_tables WHERE table_name = 'MIGRATIONS'")
    result = cursor.fetchone()
    if not result:
        cursor.execute("CREATE TABLE migrations (filename VARCHAR2(255), hash VARCHAR2(255))")
        connection.commit()
        print('Migrations table created successfully')
    cursor.close()

    print('Running migrations...')
    migration_files = get_migration_files()
    print(f"Found {len(migration_files)} migration files")
    for file in migration_files:
        hash = get_migration_hash(file)
        status = get_migration_status(file)
        if status:
            if status[1] != hash:
                raise Exception(f"Migration {file} has been run before, but the hash has changed")
            else:
                print(f"Migration {file} has already been run")
        else:
            run_migration(file)
            add_migration_to_table(file, hash)
            print(f"Migration {file} has been run successfully")
    print('All migrations have been run successfully')

    connection.close()
    
    # Move back to parent directory
    os.chdir('..')

if __name__ == '__main__':
    main()