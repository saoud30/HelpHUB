# --- START OF FILE dashboard.py (Final Version) ---

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
import requests # To make API calls
import json
import os
from datetime import datetime, timedelta

from database_manager import db_manager
db = db_manager

# We need the GROQ key here as well for the root cause analysis
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# --- LLM function for Root Cause Analysis ---
def get_llm_root_cause(summaries: str) -> str:
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not configured."
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    Based on the following list of customer support ticket summaries, what is the likely single root cause or common theme?
    Provide a concise, one-paragraph analysis written for a business manager. Focus on the core problem.

    Summaries:
    - {summaries}
    """
    data = {"model": "llama3-70b-8192", "messages": [{"role": "user", "content": prompt}], "temperature": 0.5}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Error analyzing root cause: {e}"

# (Data fetching and charting functions)
def get_stats_data():
    stats = db.get_ticket_stats()
    return stats['total'], stats['open'], stats['resolved'], stats['forwarded']

def get_category_pie_chart():
    data = db.get_category_distribution()
    if not data: return go.Figure().update_layout(title_text="No Category Data Available", template="plotly_dark")
    fig = go.Figure(data=[go.Pie(labels=list(data.keys()), values=list(data.values()), hole=.4, pull=[0.05] * len(data.keys()), marker=dict(colors=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']), textinfo='percent+label')])
    fig.update_layout(title_text='📊 Category Distribution', font=dict(family="Arial, sans-serif"), showlegend=False, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
    return fig

def get_priority_bar_chart():
    data = db.get_priority_distribution()
    if not data: return go.Figure().update_layout(title_text="No Priority Data Available", template="plotly_dark")
    color_map = {'High': '#d62728', 'Medium': '#ff7f0e', 'Low': '#2ca02c'}
    priority_order = ['High', 'Medium', 'Low']
    labels = [p for p in priority_order if p in data]
    values = [data[p] for p in labels]
    bar_colors = [color_map.get(p) for p in labels]
    fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color=bar_colors, text=values, textposition='auto')])
    fig.update_layout(title_text='📈 Priority Breakdown', xaxis_title=None, yaxis_title="Ticket Count", template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
    return fig

def get_ticket_volume_chart(timeframe_days=7):
    end_date, start_date = datetime.now(), datetime.now() - timedelta(days=timeframe_days)
    tickets = db.get_tickets_by_date_range(start_date.isoformat(), end_date.isoformat())
    if not tickets: return go.Figure().update_layout(title_text=f"No Ticket Data for Last {timeframe_days} Days", template="plotly_dark")
    df = pd.DataFrame(tickets)
    df['created_at'] = pd.to_datetime(df['created_at'])
    daily_counts = df.set_index('created_at').resample('D').size().reset_index(name='count')
    date_range = pd.date_range(start=start_date.date(), end=end_date.date())
    daily_counts = daily_counts.set_index('created_at').reindex(date_range, fill_value=0).reset_index().rename(columns={'index': 'date'})
    fig = go.Figure(data=go.Scatter(x=daily_counts['date'], y=daily_counts['count'], mode='lines+markers', fill='tozeroy', line=dict(color='#1f77b4', width=2), marker=dict(size=8)))
    fig.update_layout(title_text=f'📅 Ticket Volume (Last {timeframe_days} Days)', xaxis_title='Date', yaxis_title='New Tickets', template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
    return fig

# --- THE FIX IS IN THIS FUNCTION ---
def format_recent_activity():
    activities = db.get_recent_activity(limit=10)
    if not activities:
        return "No recent activity."
        
    feed = ""
    # The corrected dictionary
    status_icons = {"open": "🟡", "resolved": "✅", "forwarded": "🔄"}
    
    for act in activities:
        # Correctly using the dictionary here
        icon = status_icons.get(act.get('status'), '🆕') 
        timestamp = pd.to_datetime(act.get('created_at')).strftime('%b %d, %H:%M')
        feed += f"**{icon} {act.get('id')}** ({act.get('status', 'N/A').title()}) created by *{act.get('username', 'N/A')}* at {timestamp}\n---\n"
    return feed

def get_filtered_tickets(status_filter, search_term):
    if search_term: tickets = db.search_tickets(search_term)
    else: tickets = db.get_all_tickets(status=status_filter if status_filter.lower() != "all" else None, limit=200)
    if not tickets: return pd.DataFrame(columns=['ID', 'Status', 'Priority', 'Category', 'Username', 'Summary']), []
    display_data = [{'ID': t.get('id'), 'Status': t.get('status', 'N/A').title(), 'Priority': t.get('priority', 'N/A'), 'Category': t.get('category', 'N/A'), 'Username': t.get('username', 'N/A'), 'Summary': t.get('summary', 'N/A')} for t in tickets]
    return pd.DataFrame(display_data), tickets

# --- Gradio UI Definition ---
with gr.Blocks(theme=gr.themes.Base(primary_hue="blue"), title="HelpHub AI Dashboard") as dashboard:
    raw_tickets_state = gr.State([])
    with gr.Row():
        gr.Markdown("# 🚀 HelpHub AI - Support Dashboard")
        refresh_button = gr.Button("🔄 Refresh All", variant="secondary")
    with gr.Tabs() as tabs:
        with gr.TabItem("📊 Main Dashboard", id=0):
            with gr.Row():
                open_kpi, resolved_kpi, forwarded_kpi, total_kpi = [gr.Button("Loading...") for _ in range(4)]
            with gr.Row():
                with gr.Column(scale=2):
                    gr.Markdown("### 📅 Ticket Volume")
                    timeframe_selector = gr.Radio(["7 Days", "30 Days"], value="7 Days", label="Select Timeframe", interactive=True)
                    ticket_volume_chart = gr.Plot()
                with gr.Column(scale=1):
                    gr.Markdown("### 📢 Recent Activity")
                    activity_feed = gr.Markdown("Loading activity...")
            with gr.Row():
                category_chart = gr.Plot()
                priority_chart = gr.Plot()
            with gr.Group():
                gr.Markdown("### 🧠 AI Root Cause Analysis")
                with gr.Row():
                    analysis_category = gr.Dropdown(choices=db.get_all_categories(), label="Select Category to Analyze", interactive=True)
                    analyze_button = gr.Button("Analyze", variant="primary")
                analysis_result = gr.Markdown("Select a category and click 'Analyze' to see AI-powered insights.", visible=True)
        with gr.TabItem("🎟️ Ticket Management", id=1):
            with gr.Row():
                with gr.Column(scale=3):
                    gr.Markdown("### 🎟️ Ticket Browser")
                    with gr.Row():
                        status_filter = gr.Dropdown(["all", "open", "resolved", "forwarded"], label="Filter by Status", value="all", interactive=True)
                        search_box = gr.Textbox(placeholder="Search by Keyword or Ticket ID...", show_label=False, interactive=True)
                    ticket_df = gr.DataFrame(headers=['ID', 'Status', 'Priority', 'Category', 'Username', 'Summary'], datatype=['str']*6, interactive=True)
                with gr.Column(scale=2, visible=False) as detail_view:
                    gr.Markdown("### 📝 Ticket Details")
                    selected_ticket_id = gr.Textbox(label="Ticket ID", interactive=False)
                    with gr.Accordion("Full Issue Description", open=False): issue_text = gr.Markdown()
                    with gr.Row(): username_text, created_at_text = gr.Textbox(label="Username", interactive=False), gr.Textbox(label="Created At", interactive=False)
                    summary_text = gr.Textbox(label="AI Summary", interactive=False, lines=3)
                    gr.Markdown("#### **Agent Actions**")
                    with gr.Row():
                        update_status_radio = gr.Radio(["open", "resolved", "forwarded"], label="Update Status")
                        assigned_to_text = gr.Textbox(label="Assign To", placeholder="e.g., agent_bob")
                    resolution_text = gr.Textbox(label="Resolution Note", placeholder="e.g., 'User issue resolved by clearing cache.'")
                    update_button = gr.Button("Update Ticket", variant="primary")
                    update_feedback = gr.Markdown()

    # Event Handlers
    def load_all_data():
        total, open_t, resolved, forwarded = get_stats_data()
        kpi_buttons = [f"🟡 Open\n{open_t}", f"✅ Resolved\n{resolved}", f"🔄 Forwarded\n{forwarded}", f"🎫 Total\n{total}"]
        df, raw_tickets = get_filtered_tickets("all", "")
        return *kpi_buttons, get_category_pie_chart(), get_priority_bar_chart(), get_ticket_volume_chart(7), format_recent_activity(), df, raw_tickets
    
    def refresh_ticket_list(status, search):
        df, raw_tickets = get_filtered_tickets(status, search); return df, raw_tickets
    
    def filter_by_kpi(status):
        df, raw_tickets = get_filtered_tickets(status, ""); return {ticket_df: df, raw_tickets_state: raw_tickets, status_filter: gr.Dropdown(value=status), tabs: gr.Tabs(selected=1)}

    def show_ticket_details(tickets_data, evt: gr.SelectData):
        if evt.index is None or not tickets_data: return {detail_view: gr.Column(visible=False)}
        selected_ticket = tickets_data[evt.index[0]]
        return {detail_view: gr.Column(visible=True), selected_ticket_id: selected_ticket.get('id', 'N/A'), issue_text: selected_ticket.get('issue', 'N/A'), username_text: selected_ticket.get('username', 'N/A'), created_at_text: selected_ticket.get('created_at', 'N/A')[:19].replace('T', ' '), summary_text: selected_ticket.get('summary', 'N/A'), update_status_radio: selected_ticket.get('status', 'open'), assigned_to_text: selected_ticket.get('assigned_to', ''), resolution_text: selected_ticket.get('resolution', ''), update_feedback: ""}

    def update_ticket_action(ticket_id, new_status, resolution, assigned_to, current_status_filter, current_search):
        if not ticket_id: return {update_feedback: gr.Markdown("❌ No ticket selected.")}
        ticket = db.get_ticket(ticket_id)
        if not ticket: return {update_feedback: gr.Markdown("❌ Ticket not found.")}
        db.update_ticket_status(ticket_id, new_status, resolution)
        if assigned_to: db.assign_ticket(ticket_id, assigned_to)
        if new_status == "resolved" and resolution and ticket.get('user_id'):
            try: requests.post("http://127.0.0.1:8000/notify_user", json={"user_id": ticket.get('user_id'), "message": f"✅ Your ticket **{ticket_id}** has been resolved!\n\n**Agent Note:**\n_{resolution}_"}, timeout=5)
            except requests.exceptions.RequestException as e: print(f"Could not notify user: {e}")
        df, raw_tickets = get_filtered_tickets(current_status_filter, current_search)
        return {update_feedback: gr.Markdown("✅ Ticket updated successfully!"), ticket_df: df, raw_tickets_state: raw_tickets}
    
    def perform_root_cause_analysis(category):
        if not category: yield "Please select a category first."; return
        yield "🧠 Analyzing summaries... please wait."; summaries = db.get_summaries_by_category(category)
        if len(summaries) < 3: yield f"Not enough data. Need at least 3 tickets in '{category}' to analyze."; return
        yield get_llm_root_cause("\n- ".join(summaries))

    # Connect components
    dashboard.load(load_all_data, outputs=[open_kpi, resolved_kpi, forwarded_kpi, total_kpi, category_chart, priority_chart, ticket_volume_chart, activity_feed, ticket_df, raw_tickets_state])
    refresh_button.click(load_all_data, outputs=[open_kpi, resolved_kpi, forwarded_kpi, total_kpi, category_chart, priority_chart, ticket_volume_chart, activity_feed, ticket_df, raw_tickets_state])
    status_filter.change(refresh_ticket_list, inputs=[status_filter, search_box], outputs=[ticket_df, raw_tickets_state])
    search_box.submit(refresh_ticket_list, inputs=[status_filter, search_box], outputs=[ticket_df, raw_tickets_state])
    timeframe_selector.change(get_ticket_volume_chart, inputs=timeframe_selector, outputs=ticket_volume_chart)
    open_kpi.click(lambda: filter_by_kpi("open"), outputs=[ticket_df, raw_tickets_state, status_filter, tabs])
    resolved_kpi.click(lambda: filter_by_kpi("resolved"), outputs=[ticket_df, raw_tickets_state, status_filter, tabs])
    forwarded_kpi.click(lambda: filter_by_kpi("forwarded"), outputs=[ticket_df, raw_tickets_state, status_filter, tabs])
    total_kpi.click(lambda: filter_by_kpi("all"), outputs=[ticket_df, raw_tickets_state, status_filter, tabs])
    ticket_df.select(show_ticket_details, inputs=[raw_tickets_state], outputs=[detail_view, selected_ticket_id, issue_text, username_text, created_at_text, summary_text, update_status_radio, assigned_to_text, resolution_text, update_feedback])
    update_button.click(update_ticket_action, inputs=[selected_ticket_id, update_status_radio, resolution_text, assigned_to_text, status_filter, search_box], outputs=[update_feedback, ticket_df, raw_tickets_state])
    analyze_button.click(perform_root_cause_analysis, inputs=[analysis_category], outputs=[analysis_result])

# Launch the Dashboard
if __name__ == "__main__":
    dashboard.launch(share=True)
# --- END OF FILE dashboard.py ---