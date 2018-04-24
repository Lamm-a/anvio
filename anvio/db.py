# -*- coding: utf-8
# pylint: disable=line-too-long
"""
    Low-level db operations.
"""

import os
import sqlite3
import pandas as pd

import anvio
import anvio.tables as tables
import anvio.filesnpaths as filesnpaths

from anvio.errors import ConfigError


__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2018, the Meren Lab (http://merenlab.org/)"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "A. Murat Eren"
__email__ = "a.murat.eren@gmail.com"
__status__ = "Development"


class DB:
    def __init__(self, db_path, client_version, new_database=False, ignore_version=False):
        self.db_path = db_path
        self.version = None

        if new_database:
            filesnpaths.is_output_file_writable(db_path)
        else:
            filesnpaths.is_file_exists(db_path)

        if new_database and os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.text_factory = str

        self.cursor = self.conn.cursor()

        if new_database:
            self.create_self()
            self.set_version(client_version)
        else:
            self.version = self.get_version()
            if str(self.version) != str(client_version) and not ignore_version:
                if int(self.version) > int(client_version):
                    raise ConfigError("Bad news of the day: the database at %s was generated with an anvi'o version that is 'newer' than\
                                       the one you are actively using right now. We know, you hate to hear this, but you need to upgrade\
                                       your anvi'o :(" % self.db_path)
                else:
                    raise ConfigError("The database at '%s' is outdated (its version is v%s, but your anvi'o installation only knows how to\
                                       deal with v%s). You can migrate your database without losing any data using the program `anvi-migrate-db`."\
                                               % (self.db_path, self.version, client_version))


    def get_version(self):
        try:
            return self.get_meta_value('version')
        except:
            raise ConfigError("%s does not seem to be a database generated by anvi'o :/" % self.db_path)


    def create_self(self):
        self._exec('''CREATE TABLE self (key text, value text)''')


    def drop_table(self, table_name):
        self._exec('''DROP TABLE IF EXISTS %s;''' % table_name)


    def create_table(self, table_name, fields, types):
        if len(fields) != len(types):
            raise ConfigError("create_table: The number of fields and types has to match.")

        db_fields = ', '.join(['%s %s' % (t[0], t[1]) for t in zip(fields, types)])
        self._exec('''CREATE TABLE %s (%s)''' % (table_name, db_fields))
        self.commit()


    def set_version(self, version):
        self.set_meta_value('version', version)
        self.commit()


    def set_meta_value(self, key, value):
        self.remove_meta_key_value_pair(key)
        self._exec('''INSERT INTO self VALUES(?,?)''', (key, value,))
        self.commit()


    def remove_meta_key_value_pair(self, key):
        self._exec('''DELETE FROM self WHERE key="%s"''' % key)
        self.commit()


    def update_meta_value(self, key, value):
        self.remove_meta_key_value_pair(key)
        self.set_meta_value(key, value)


    def copy_paste(self, table_name, source_db_path):
        """Copy `table_name` data from another database (`source_db_path`) into yourself"""

        source_db = DB(source_db_path, None, ignore_version=True)
        data = source_db.get_all_rows_from_table(table_name)

        if not len(data):
            return

        self._exec('''DELETE FROM %s''' % table_name)
        self._exec_many('''INSERT INTO %s VALUES(%s)''' % (table_name, ','.join(['?'] * len(data[0]))), data)


    def get_max_value_in_column(self, table_name, column_name):
        response = self._exec("""SELECT MAX(%s) FROM %s""" % (column_name, table_name))
        rows = response.fetchall()

        val = rows[0][0]

        if isinstance(val, type(None)):
            return None

        try:
            val = int(val)
        except ValueError:
            pass

        return val


    def get_meta_value(self, key):
        response = self._exec("""SELECT value FROM self WHERE key='%s'""" % key)
        rows = response.fetchall()

        if not rows:
            raise ConfigError("A value for '%s' does not seem to be set in table 'self'." % key)

        val = rows[0][0]

        if isinstance(val, type(None)):
            return None

        try:
            val = int(val)
        except ValueError:
            pass

        return val


    def commit(self):
        self.conn.commit()


    def disconnect(self):
        self.conn.commit()
        self.conn.close()


    def _exec(self, sql_query, value=None):
        if value:
            ret_val = self.cursor.execute(sql_query, value)
        else:
            ret_val = self.cursor.execute(sql_query)

        self.commit()
        return ret_val


    def _exec_many(self, sql_query, values):
        return self.cursor.executemany(sql_query, values)


    def insert(self, table_name, values=()):
        query = '''INSERT INTO %s VALUES (%s)''' % (table_name, ','.join(['?'] * len(values)))
        return self._exec(query, values)


    def insert_many(self, table_name, entries=None):
        if len(entries):
            query = '''INSERT INTO %s VALUES (%s)''' % (table_name, ','.join(['?'] * len(entries[0])))
            return self._exec_many(query, entries)


    def get_all_rows_from_table(self, table):
        response = self._exec('''SELECT * FROM %s''' % table)
        return response.fetchall()


    def get_row_counts_from_table(self, table, where_clause=None):
        if where_clause:
            response = self._exec('''SELECT COUNT(*) FROM %s WHERE %s''' % (table, where_clause))
        else:
            response = self._exec('''SELECT COUNT(*) FROM %s''' % (table))

        return response.fetchall()[0][0]


    def get_some_rows_from_table(self, table, where_clause):
        response = self._exec('''SELECT * FROM %s WHERE %s''' % (table, where_clause))
        return response.fetchall()


    def get_single_column_from_table(self, table, column, unique=False, where_clause=None):
        if where_clause:
            response = self._exec('''SELECT %s %s FROM %s WHERE %s''' % ('DISTINCT' if unique else '', column, table, where_clause))
        else:
            response = self._exec('''SELECT %s %s FROM %s''' % ('DISTINCT' if unique else '', column, table))
        return [t[0] for t in response.fetchall()]


    def get_table_column_types(self, table):
        response = self._exec('PRAGMA TABLE_INFO(%s)' % table)
        return [t[2] for t in response.fetchall()]


    def get_table_structure(self, table):
        response = self._exec('''SELECT * FROM %s''' % table)
        return [t[0] for t in response.description]


    def get_table_as_list_of_tuples(self, table, table_structure=None):
        return self.get_all_rows_from_table(table)


    def get_table_as_dict(self, table, table_structure=None, string_the_key=False, columns_of_interest=None, keys_of_interest=None, omit_parent_column=False, error_if_no_data=True):
        if not table_structure:
            table_structure = self.get_table_structure(table)

        columns_to_return = list(range(0, len(table_structure)))

        if omit_parent_column:
            if '__parent__' in table_structure:
                columns_to_return.remove(table_structure.index('__parent__'))
                table_structure.remove('__parent__')

        if columns_of_interest:
            for col in table_structure[1:]:
                if col not in columns_of_interest:
                    columns_to_return.remove(table_structure.index(col))

        if len(columns_to_return) == 1:
            if error_if_no_data:
                raise ConfigError("get_table_as_dict :: after removing an column that was not mentioned in the columns\
                                    of interest by the client, nothing was left to return...")
            else:
                return {}

        if keys_of_interest:
            keys_of_interest = set(keys_of_interest)

        results_dict = {}

        rows = self.get_all_rows_from_table(table)

        if table not in tables.tables_without_unique_entry_ids:
            unique_keys = set([r[0] for r in rows])
            if len(unique_keys) != len(rows):
                raise ConfigError("This is one of the core functions of anvi'o you never want to hear from, but there seems\
                                   to be something wrong with the table '%s' that you are trying to read from. While there\
                                   are %d items in this table, there are only %d unique keys, which means some of them are\
                                   going to be overwritten when this function creates a final dictionary of data to return.\
                                   This may be a programmer error when the data was being inserted into the database, but\
                                   needs fixin' before we can continue. If you are a user, please get in touch with anvi'o\
                                   developers about this error. If you are a programmer, you probably did something\
                                   wrong :(" % (table, len(rows), len(unique_keys)))

        for row in rows:
            entry = {}

            if keys_of_interest:
                if row[0] in keys_of_interest:
                    # so we are interested in keeping this, reduce the size of the
                    # hash size to improve the next inquiry, and keep going.
                    keys_of_interest.remove(row[0])
                else:
                    # we are not intersted in this one, continue:
                    continue

            for i in columns_to_return[1:]:
                entry[table_structure[i]] = row[i]

            if string_the_key:
                results_dict[str(row[0])] = entry
            else:
                results_dict[row[0]] = entry

        return results_dict


    def get_table_as_dataframe(self, table, table_structure=None, columns_of_interest=None, keys_of_interest=None, omit_parent_column=False, error_if_no_data=True):
        """
        get_table_as_dict() uses the first column as the key in the resulting
        dictionary. For pandas DataFrames there are two reasonable design
        approaches. The first mimics this approach and uses the first column as
        the index of the DataFrame. The approach I take instead is to keep the
        first column as a column in the DataFrame (it is afterall, a column)
        and use numerical indices for the DataFrame.
        """
        if not table_structure:
            table_structure = self.get_table_structure(table)

        columns_to_return = table_structure

        if omit_parent_column:
            if '__parent__' in table_structure:
                columns_to_return.remove('__parent__')
                table_structure.remove('__parent__')

        if columns_of_interest:
            for col in table_structure[1:]:
                if col not in columns_of_interest:
                    columns_to_return.remove(col)

        if len(columns_to_return) == 1:
            if error_if_no_data:
                raise ConfigError("get_table_as_dataframe :: after removing an column that was not mentioned in the columns\
                                    of interest by the client, nothing was left to return...")
            else:
                return {}

        if keys_of_interest:
            keys_of_interest = set(keys_of_interest)

        rows = self.get_all_rows_from_table(table)
        results_df = pd.DataFrame(rows, columns=table_structure)

        if keys_of_interest:
            results_df = results_df.loc[results_df.index.isin(keys_of_interest)]
        results_df = results_df.loc[:, columns_to_return]

        return results_df


    def get_some_rows_from_table_as_dict(self, table, where_clause, error_if_no_data=True, string_the_key=False):
        """This is similar to get_table_as_dict, but much less general.

           get_table_as_dict can do a lot, but it first reads all data into the memory to operate on it.
           In some cases the programmer may like to access to only a small fraction of entries in a table
           by using `WHERE column = value` notation, which is not possible with the more generalized
           function."""

        results_dict = {}

        table_structure = self.get_table_structure(table)
        columns_to_return = list(range(0, len(table_structure)))

        rows = self._exec('''SELECT * FROM %s WHERE %s''' % (table, where_clause)).fetchall()

        for row in rows:
            entry = {}

            for i in columns_to_return[1:]:
                entry[table_structure[i]] = row[i]

            if string_the_key:
                results_dict[str(row[0])] = entry
            else:
                results_dict[row[0]] = entry

        if error_if_no_data and not len(results_dict):
            raise ConfigError("Query on %s with the where clause of '%s' did not return anything." % (table, where_clause))

        return results_dict


    def get_table_names(self):
        response = self._exec("""select name from sqlite_master where type='table'""")
        return [r[0] for r in response.fetchall()]
