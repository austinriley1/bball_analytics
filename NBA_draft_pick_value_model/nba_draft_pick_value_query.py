import pandas as pd
import psycopg2
import pandas.io.sql as sqlio

connection = psycopg2.connect(user="postgres.rleeydkzagekalphrqwi",
                              password="Stratocastertelecaster1!",
                              host="aws-0-us-east-1.pooler.supabase.com",
                              # port="5432",
                              database="postgres")
cursor = connection.cursor()
cursor.execute("SELECT * FROM public.nba_draft_pick_value;")
# Retrieve query results
records = cursor.fetchall()
owned_draft_pick_value = sqlio.read_sql_query("SELECT * FROM public.nba_draft_pick_value;", connection)
owned_draft_pick_value