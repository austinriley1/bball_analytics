from dash import Dash, html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
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

app = Dash(external_stylesheets=[dbc.themes.BOOTSTRAP])

base_grid_options = {
    "theme": {"function": "themeAlpine.withParams({backgroundColor: '#1e1e1e', foregroundColor: '#fff', headerBackgroundColor: '#2a2a2a'})"},
    "animateRows": True,
    "pinnedBottomRowData": [],
    "context": {"valueMin": 0, "valueMax": 1},
}

# columnDefs are now STATIC — cellStyle reads min/max from context at runtime, not baked in
column_defs = [
    {"field": "originating team"},
    {"field": "year"},
    {"field": "round"},
    {"field": "rights holder"},
    {"field": "notes"},
    {
        "field": "value",
        "valueFormatter": {"function": "d3.format(',.2f')(params.value)"},
        "cellStyle": {"function": "valueGradient(params)"},
    },
    {"field": "% of league value", "valueFormatter": {"function": "d3.format(',.2f')(params.value)"}},
]

app.layout = html.Div([

    html.Div([
        html.H1("NBA Draft Pick Value", style={
            "backgroundColor": "#1e1e1e",
            "color": "#fff",
            "padding": "15px",
            "borderRadius": "6px",
            "fontFamily": "Helvetica, sans-serif",
            "fontSize": "40px",
            "margin": "0",
        }),
        html.P(
            "Value is based on an adjusted composite of player value metrics over their first four seasons set on a scale from 0-10, 10 being equivalent to the value of a player who ranked first in the league in all advanced stat categories in a season. The value of the 1st overall pick is 4.06, roughly equivalent to that of players such as Kon Knueppel, De'Aaron Fox, Zach Edey, and Lauri Markkanen. All picks beyond 2029 are valued at the middle of each round.",
            style={
                "color": "#ccc",
                "fontSize": "12px",
                "margin": "0",
                "maxWidth": "450px",
                "marginTop": "10px",
                "marginRight": "80px",
                "textAlign": "left",
            }
        ),
    ], style={
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "center",
        "backgroundColor": "#1e1e1e",
        "padding": "15px",
        "borderRadius": "6px",
    }),

    dbc.Container([
        dbc.Row([
            dbc.Col(dcc.Dropdown(
                owned_draft_pick_value['originating team'].unique(),
                id='origin-dropdown', value=[], multi=True, closeOnSelect=True,
                style={'height': '30px', 'width': '200px','color':'black'}, placeholder="Originating Team",
            ), width="auto"),
            dbc.Col(dcc.Dropdown(
                owned_draft_pick_value['rights holder'].unique(),
                id='rights-dropdown', value=[], multi=True, closeOnSelect=True,
                style={'height': '30px', 'width': '200px','color':'black'}, placeholder="Rights Holder",
            ), width="auto"),
        ])
    ], fluid=True, style={
        "backgroundColor": "#1e1e1e",
        "color": "#fff",
        "padding": "15px",
        "borderRadius": "6px",
    }),

    dag.AgGrid(
        id='my-datatable',
        rowData=owned_draft_pick_value.to_dict('records'),
        columnDefs=column_defs,
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "flex" : 1},
        style={"flex": "1", "width": "100%"},
        dashGridOptions=base_grid_options,
        dangerously_allow_code=True,
    ),

], style={
    "backgroundColor": "#1e1e1e",
    "color": "#fff",
    "display": "flex",
    "flexDirection": "column",
    "height": "100vh",
})


@callback(
    Output('my-datatable', 'rowData'),
    Input('origin-dropdown', 'value'),
    Input('rights-dropdown', 'value')
)
def update_output(teams, rights_holders):
    filtered_df = owned_draft_pick_value
    if teams:
        filtered_df = filtered_df[filtered_df['originating team'].isin(teams)]
    if rights_holders:
        filtered_df = filtered_df[filtered_df['rights holder'].isin(rights_holders)]
    return filtered_df.to_dict('records')


# Single callback now handles BOTH the pinned total row AND the gradient's min/max context,
# since both depend on whatever rows are currently visible (virtualRowData).
@callback(
    Output('my-datatable', 'dashGridOptions'),
    Input('my-datatable', 'virtualRowData')
)
def update_grid_options(virtual_data):
    total_value = 0
    total_pct_value = 0
    value_min = 0
    value_max = 1

    if virtual_data:
        df_current = pd.DataFrame(virtual_data)
        total_value = round(df_current["value"].sum(), 2)
        total_pct_value = round(df_current["% of league value"].sum(), 2)
        value_min = float(df_current["value"].min())
        value_max = float(df_current["value"].max())

    total_row = [{
        'originating team': 'Total',
        'year': 0,
        'round': 0,
        'rights holder': '',
        'notes': '',
        'value': total_value,
        '% of league value': total_pct_value
    }]

    updated_options = dict(base_grid_options)
    updated_options["pinnedBottomRowData"] = total_row
    updated_options["context"] = {"valueMin": value_min, "valueMax": value_max}
    return updated_options


if __name__ == '__main__':
    app.run(debug=True, port=8050)