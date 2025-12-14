"""
Web Dashboard for ErixCast Bot Analytics
Simple Flask-based dashboard for admin analytics
"""
try:
    from flask import Flask, render_template_string, jsonify
    flask_available = True
except ImportError:
    flask_available = False
    Flask = None

try:
    from services.analytics_service import analytics_service
except ImportError:
    analytics_service = None
import os
import logging

logger = logging.getLogger(__name__)

if flask_available:
    app = Flask(__name__)
else:
    app = None

# Dashboard HTML template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ErixCast Bot - Dashboard Analytics</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 2.5em; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; }
        .chart-container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .chart-title { font-size: 1.2em; margin-bottom: 15px; color: #333; }
        .health-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .health-good { background: #4CAF50; }
        .health-warning { background: #FF9800; }
        .health-error { background: #F44336; }
        .refresh-btn { background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; margin: 10px; }
        .refresh-btn:hover { background: #5a6fd8; }
        .export-btn { background: #4CAF50; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; margin: 5px; }
        .loading { text-align: center; padding: 50px; color: #666; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 ErixCast Bot Analytics</h1>
        <p>Dashboard di monitoraggio e statistiche in tempo reale</p>
    </div>
    
    <div class="container">
        <div id="loading" class="loading">
            <h3>Caricamento dati...</h3>
        </div>
        
        <div id="dashboard" style="display: none;">
            <!-- Stats Overview -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="total-users">-</div>
                    <div class="stat-label">👥 Utenti Totali</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="active-tickets">-</div>
                    <div class="stat-label">🎫 Ticket Attivi</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="total-lists">-</div>
                    <div class="stat-label">📋 Liste Totali</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="uptime">-</div>
                    <div class="stat-label">⏱️ Uptime %</div>
                </div>
            </div>
            
            <!-- AI Performance -->
            <div class="chart-container">
                <div class="chart-title">🤖 Performance AI</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number" id="ai-success-rate">-</div>
                        <div class="stat-label">Tasso Successo %</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="ai-response-time">-</div>
                        <div class="stat-label">Tempo Risposta (s)</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="ai-escalated">-</div>
                        <div class="stat-label">Auto-Escalation (7gg)</div>
                    </div>
                </div>
            </div>
            
            <!-- Daily Activity Chart -->
            <div class="chart-container">
                <div class="chart-title">📊 Attività Giornaliera (Ultimi 7 giorni)</div>
                <canvas id="dailyChart" width="400" height="200"></canvas>
            </div>
            
            <!-- System Health -->
            <div class="chart-container">
                <div class="chart-title">🏥 Stato Sistema</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <span class="health-indicator health-good"></span>
                        <span id="system-status">Sistema Operativo</span>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="memory-usage">-</div>
                        <div class="stat-label">Memoria %</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="cpu-usage">-</div>
                        <div class="stat-label">CPU %</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="error-rate">-</div>
                        <div class="stat-label">Errori %</div>
                    </div>
                </div>
            </div>
            
            <!-- Controls -->
            <div style="text-align: center; margin-top: 30px;">
                <button class="refresh-btn" onclick="loadDashboard()">🔄 Aggiorna Dati</button>
                <button class="export-btn" onclick="exportData('daily')">📊 Export Giornaliero</button>
                <button class="export-btn" onclick="exportData('weekly')">📈 Export Settimanale</button>
                <button class="export-btn" onclick="exportData('monthly')">📅 Export Mensile</button>
            </div>
        </div>
    </div>

    <script>
        let dailyChart;
        
        async function loadDashboard() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('dashboard').style.display = 'none';
            
            try {
                const response = await fetch('/api/dashboard');
                const data = await response.json();
                
                updateStats(data);
                updateCharts(data);
                
                document.getElementById('loading').style.display = 'none';
                document.getElementById('dashboard').style.display = 'block';
            } catch (error) {
                console.error('Error loading dashboard:', error);
                document.getElementById('loading').innerHTML = '<h3 style="color: red;">Errore nel caricamento dati</h3>';
            }
        }
        
        function updateStats(data) {
            document.getElementById('total-users').textContent = data.overview.total_users;
            document.getElementById('active-tickets').textContent = data.overview.active_tickets;
            document.getElementById('total-lists').textContent = data.overview.total_lists;
            document.getElementById('uptime').textContent = data.overview.uptime_percentage + '%';
            
            // AI Performance
            document.getElementById('ai-success-rate').textContent = data.ai_performance.success_rate + '%';
            document.getElementById('ai-response-time').textContent = data.ai_performance.avg_response_time + 's';
            document.getElementById('ai-escalated').textContent = data.ai_performance.auto_escalated_week;
            
            // System Health
            document.getElementById('memory-usage').textContent = data.system_health.memory_usage + '%';
            document.getElementById('cpu-usage').textContent = data.system_health.cpu_usage + '%';
            document.getElementById('error-rate').textContent = data.system_health.error_rate + '%';
        }
        
        function updateCharts(data) {
            // Daily Activity Chart
            const ctx = document.getElementById('dailyChart').getContext('2d');
            
            if (dailyChart) {
                dailyChart.destroy();
            }
            
            dailyChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.daily.map(d => d.day_name),
                    datasets: [{
                        label: 'Ticket Creati',
                        data: data.daily.map(d => d.tickets_created),
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4
                    }, {
                        label: 'Ticket Risolti',
                        data: data.daily.map(d => d.tickets_resolved),
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }
        
        async function exportData(type) {
            try {
                const response = await fetch(`/api/export/${type}`);
                const data = await response.text();
                
                const blob = new Blob([data], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `erixcast_${type}_${new Date().toISOString().split('T')[0]}.csv`;
                a.click();
                window.URL.revokeObjectURL(url);
            } catch (error) {
                console.error('Error exporting data:', error);
                alert('Errore nell\\'export dei dati');
            }
        }
        
        // Auto-refresh every 5 minutes
        setInterval(loadDashboard, 5 * 60 * 1000);
        
        // Load dashboard on page load
        loadDashboard();
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/dashboard')
def api_dashboard():
    """API endpoint for dashboard data"""
    try:
        data = analytics_service.get_dashboard_data()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in dashboard API: {e}")
        return jsonify({'error': 'Unable to load dashboard data'}), 500

@app.route('/api/export/<data_type>')
def api_export(data_type):
    """API endpoint for data export"""
    try:
        csv_data = analytics_service.export_data_csv(data_type)
        return csv_data, 200, {'Content-Type': 'text/csv'}
    except Exception as e:
        logger.error(f"Error in export API: {e}")
        return "Error exporting data", 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'dashboard'})

if __name__ == '__main__':
    if flask_available and app:
        port = int(os.getenv('DASHBOARD_PORT', 5001))
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        print("Flask not available, dashboard cannot start")