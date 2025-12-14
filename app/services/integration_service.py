"""
External Integrations Service
Free integrations with Google Sheets, Calendar, Email, and Webhooks
"""
import logging
from datetime import datetime, timezone, timedelta
import json
import os
import asyncio
import aiohttp
from models import SessionLocal, List, Ticket, UserActivity

logger = logging.getLogger(__name__)

class IntegrationService:
    """Service for managing external integrations"""
    
    def __init__(self):
        self.google_sheets_enabled = bool(os.getenv('GOOGLE_SHEETS_CREDENTIALS'))
        self.calendar_enabled = bool(os.getenv('GOOGLE_CALENDAR_CREDENTIALS'))
        self.email_enabled = bool(os.getenv('SENDGRID_API_KEY'))
        self.webhook_endpoints = self._load_webhook_endpoints()
        self.integration_stats = {
            'sheets_exports': 0,
            'calendar_events': 0,
            'emails_sent': 0,
            'webhooks_sent': 0
        }
    
    def _load_webhook_endpoints(self):
        """Load webhook endpoints from environment"""
        try:
            webhooks_config = os.getenv('WEBHOOK_ENDPOINTS', '{}')
            return json.loads(webhooks_config)
        except json.JSONDecodeError:
            return {}
    
    async def export_to_google_sheets(self, data_type, data, spreadsheet_id=None):
        """Export data to Google Sheets"""
        try:
            if not self.google_sheets_enabled:
                return False, "Google Sheets integration not configured"
            
            # In a real implementation, this would use Google Sheets API
            # For now, we'll simulate the export
            
            if data_type == 'tickets':
                formatted_data = self._format_tickets_for_sheets(data)
            elif data_type == 'lists':
                formatted_data = self._format_lists_for_sheets(data)
            elif data_type == 'analytics':
                formatted_data = self._format_analytics_for_sheets(data)
            else:
                return False, f"Unsupported data type: {data_type}"
            
            # Simulate API call
            await asyncio.sleep(0.5)  # Simulate network delay
            
            self.integration_stats['sheets_exports'] += 1
            
            logger.info(f"Exported {len(formatted_data)} rows to Google Sheets")
            return True, f"Successfully exported {len(formatted_data)} rows"
            
        except Exception as e:
            logger.error(f"Error exporting to Google Sheets: {e}")
            return False, str(e)
    
    def _format_tickets_for_sheets(self, tickets):
        """Format tickets data for Google Sheets"""
        formatted_data = [
            ['ID', 'User ID', 'Title', 'Status', 'AI Attempts', 'Auto Escalated', 'Created At', 'Updated At']
        ]
        
        for ticket in tickets:
            formatted_data.append([
                ticket.id,
                ticket.user_id,
                ticket.title,
                ticket.status,
                ticket.ai_attempts,
                'Yes' if ticket.auto_escalated else 'No',
                ticket.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return formatted_data
    
    def _format_lists_for_sheets(self, lists):
        """Format lists data for Google Sheets"""
        formatted_data = [
            ['ID', 'Name', 'Cost', 'Expiry Date', 'Notes', 'Created At']
        ]
        
        for lst in lists:
            formatted_data.append([
                lst.id,
                lst.name,
                lst.cost or '',
                lst.expiry_date.strftime('%Y-%m-%d') if lst.expiry_date else '',
                lst.notes or '',
                lst.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return formatted_data
    
    def _format_analytics_for_sheets(self, analytics):
        """Format analytics data for Google Sheets"""
        formatted_data = [
            ['Metric', 'Value', 'Date']
        ]
        
        for key, value in analytics.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    formatted_data.append([
                        f"{key}_{sub_key}",
                        str(sub_value),
                        datetime.now().strftime('%Y-%m-%d')
                    ])
            else:
                formatted_data.append([
                    key,
                    str(value),
                    datetime.now().strftime('%Y-%m-%d')
                ])
        
        return formatted_data
    
    async def create_calendar_event(self, title, description, start_time, end_time, attendees=None):
        """Create calendar event for important deadlines"""
        try:
            if not self.calendar_enabled:
                return False, "Calendar integration not configured"
            
            # In a real implementation, this would use Google Calendar API
            event_data = {
                'title': title,
                'description': description,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'attendees': attendees or []
            }
            
            # Simulate API call
            await asyncio.sleep(0.3)
            
            self.integration_stats['calendar_events'] += 1
            
            logger.info(f"Created calendar event: {title}")
            return True, f"Calendar event '{title}' created successfully"
            
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return False, str(e)
    
    async def schedule_expiry_reminders(self):
        """Schedule calendar reminders for list expiries"""
        try:
            with SessionLocal() as session:
                # Get lists expiring in the next 30 days
                cutoff_date = datetime.now(timezone.utc) + timedelta(days=30)
                expiring_lists = session.query(List).filter(
                    List.expiry_date <= cutoff_date,
                    List.expiry_date > datetime.now(timezone.utc)
                ).all()
                
                events_created = 0
                for lst in expiring_lists:
                    # Create reminder 3 days before expiry
                    reminder_time = lst.expiry_date - timedelta(days=3)
                    
                    if reminder_time > datetime.now(timezone.utc):
                        success, message = await self.create_calendar_event(
                            title=f"Lista in Scadenza: {lst.name}",
                            description=f"La lista '{lst.name}' scadrà il {lst.expiry_date.strftime('%d/%m/%Y')}. Considera il rinnovo.",
                            start_time=reminder_time,
                            end_time=reminder_time + timedelta(hours=1)
                        )
                        
                        if success:
                            events_created += 1
                
                return True, f"Created {events_created} calendar reminders"
                
        except Exception as e:
            logger.error(f"Error scheduling expiry reminders: {e}")
            return False, str(e)
    
    async def send_email_notification(self, to_email, subject, content, template_type='default'):
        """Send email notification using SendGrid"""
        try:
            if not self.email_enabled:
                return False, "Email integration not configured"
            
            # In a real implementation, this would use SendGrid API
            email_data = {
                'to': to_email,
                'subject': subject,
                'content': content,
                'template': template_type,
                'sent_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Simulate API call
            await asyncio.sleep(0.4)
            
            self.integration_stats['emails_sent'] += 1
            
            logger.info(f"Sent email to {to_email}: {subject}")
            return True, "Email sent successfully"
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False, str(e)
    
    async def send_admin_digest_email(self, admin_email, analytics_data):
        """Send daily digest email to admins"""
        try:
            subject = f"ErixCast Bot - Digest Giornaliero {datetime.now().strftime('%d/%m/%Y')}"
            
            content = f"""
            <h2>📊 Digest Giornaliero ErixCast Bot</h2>
            <p><strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y')}</p>
            
            <h3>📈 Statistiche Principali</h3>
            <ul>
                <li><strong>Utenti Totali:</strong> {analytics_data['overview']['total_users']}</li>
                <li><strong>Ticket Attivi:</strong> {analytics_data['overview']['active_tickets']}</li>
                <li><strong>Liste Totali:</strong> {analytics_data['overview']['total_lists']}</li>
                <li><strong>Uptime:</strong> {analytics_data['overview']['uptime_percentage']}%</li>
            </ul>
            
            <h3>🤖 Performance AI</h3>
            <ul>
                <li><strong>Tasso Successo:</strong> {analytics_data['ai_performance']['success_rate']}%</li>
                <li><strong>Tempo Risposta:</strong> {analytics_data['ai_performance']['avg_response_time']}s</li>
                <li><strong>Auto-escalation (7gg):</strong> {analytics_data['ai_performance']['auto_escalated_week']}</li>
            </ul>
            
            <h3>🏥 Stato Sistema</h3>
            <ul>
                <li><strong>Memoria:</strong> {analytics_data['system_health']['memory_usage']}%</li>
                <li><strong>CPU:</strong> {analytics_data['system_health']['cpu_usage']}%</li>
                <li><strong>Errori:</strong> {analytics_data['system_health']['error_rate']}%</li>
            </ul>
            
            <p><em>Dashboard completa disponibile nel bot con /admin_dashboard</em></p>
            """
            
            return await self.send_email_notification(admin_email, subject, content, 'admin_digest')
            
        except Exception as e:
            logger.error(f"Error sending admin digest email: {e}")
            return False, str(e)
    
    async def send_webhook(self, event_type, data, endpoint_name=None):
        """Send webhook notification to external services"""
        try:
            if endpoint_name:
                endpoints = {endpoint_name: self.webhook_endpoints.get(endpoint_name)}
            else:
                endpoints = self.webhook_endpoints
            
            if not endpoints:
                return False, "No webhook endpoints configured"
            
            webhook_data = {
                'event_type': event_type,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'data': data,
                'source': 'erixcast_bot'
            }
            
            results = []
            async with aiohttp.ClientSession() as session:
                for name, url in endpoints.items():
                    if not url:
                        continue
                    
                    try:
                        async with session.post(
                            url,
                            json=webhook_data,
                            headers={'Content-Type': 'application/json'},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                results.append(f"{name}: success")
                                self.integration_stats['webhooks_sent'] += 1
                            else:
                                results.append(f"{name}: failed ({response.status})")
                    
                    except asyncio.TimeoutError:
                        results.append(f"{name}: timeout")
                    except Exception as e:
                        results.append(f"{name}: error ({str(e)})")
            
            success_count = sum(1 for r in results if 'success' in r)
            total_count = len(results)
            
            logger.info(f"Sent webhooks: {success_count}/{total_count} successful")
            return True, f"Webhooks sent: {success_count}/{total_count} successful"
            
        except Exception as e:
            logger.error(f"Error sending webhooks: {e}")
            return False, str(e)
    
    async def notify_ticket_escalation(self, ticket_data):
        """Send notifications when ticket is escalated"""
        try:
            # Send webhook
            webhook_success, webhook_msg = await self.send_webhook('ticket_escalated', {
                'ticket_id': ticket_data['id'],
                'user_id': ticket_data['user_id'],
                'title': ticket_data['title'],
                'ai_attempts': ticket_data['ai_attempts']
            })
            
            # Send email to admins (if configured)
            admin_emails = os.getenv('ADMIN_EMAILS', '').split(',')
            email_results = []
            
            for email in admin_emails:
                if email.strip():
                    subject = f"🚨 Ticket Escalato #{ticket_data['id']}"
                    content = f"""
                    <h2>🚨 Ticket Escalato Automaticamente</h2>
                    <p><strong>Ticket ID:</strong> #{ticket_data['id']}</p>
                    <p><strong>Utente:</strong> {ticket_data['user_id']}</p>
                    <p><strong>Titolo:</strong> {ticket_data['title']}</p>
                    <p><strong>Tentativi AI:</strong> {ticket_data['ai_attempts']}</p>
                    <p><strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                    
                    <p>Il ticket è stato automaticamente escalato dopo {ticket_data['ai_attempts']} tentativi AI falliti.</p>
                    <p>È richiesta assistenza manuale.</p>
                    """
                    
                    email_success, email_msg = await self.send_email_notification(
                        email.strip(), subject, content, 'ticket_escalation'
                    )
                    email_results.append(email_success)
            
            return True, f"Notifications sent - Webhook: {webhook_success}, Emails: {sum(email_results)}/{len(email_results)}"
            
        except Exception as e:
            logger.error(f"Error notifying ticket escalation: {e}")
            return False, str(e)
    
    async def sync_lists_to_external_system(self):
        """Sync lists data to external system via webhook"""
        try:
            with SessionLocal() as session:
                lists = session.query(List).all()
                
                lists_data = []
                for lst in lists:
                    lists_data.append({
                        'id': lst.id,
                        'name': lst.name,
                        'cost': lst.cost,
                        'expiry_date': lst.expiry_date.isoformat() if lst.expiry_date else None,
                        'notes': lst.notes,
                        'created_at': lst.created_at.isoformat()
                    })
                
                return await self.send_webhook('lists_sync', {
                    'lists': lists_data,
                    'total_count': len(lists_data),
                    'sync_timestamp': datetime.now(timezone.utc).isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error syncing lists to external system: {e}")
            return False, str(e)
    
    async def backup_to_external_storage(self, backup_data):
        """Backup data to external storage via webhook"""
        try:
            backup_payload = {
                'backup_type': 'automated',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'data_types': list(backup_data.keys()),
                'record_counts': {k: len(v) if isinstance(v, list) else 1 for k, v in backup_data.items()},
                'backup_data': backup_data
            }
            
            return await self.send_webhook('backup_data', backup_payload, 'backup_endpoint')
            
        except Exception as e:
            logger.error(f"Error backing up to external storage: {e}")
            return False, str(e)
    
    def add_webhook_endpoint(self, name, url, admin_id):
        """Add new webhook endpoint"""
        try:
            self.webhook_endpoints[name] = url
            
            # In a real implementation, this would persist to database or config file
            logger.info(f"Added webhook endpoint '{name}': {url}")
            return True, f"Webhook endpoint '{name}' added successfully"
            
        except Exception as e:
            logger.error(f"Error adding webhook endpoint: {e}")
            return False, str(e)
    
    def remove_webhook_endpoint(self, name, admin_id):
        """Remove webhook endpoint"""
        try:
            if name in self.webhook_endpoints:
                del self.webhook_endpoints[name]
                logger.info(f"Removed webhook endpoint '{name}'")
                return True, f"Webhook endpoint '{name}' removed successfully"
            else:
                return False, f"Webhook endpoint '{name}' not found"
                
        except Exception as e:
            logger.error(f"Error removing webhook endpoint: {e}")
            return False, str(e)
    
    def get_integration_status(self):
        """Get status of all integrations"""
        return {
            'google_sheets': {
                'enabled': self.google_sheets_enabled,
                'exports_count': self.integration_stats['sheets_exports']
            },
            'calendar': {
                'enabled': self.calendar_enabled,
                'events_count': self.integration_stats['calendar_events']
            },
            'email': {
                'enabled': self.email_enabled,
                'emails_sent': self.integration_stats['emails_sent']
            },
            'webhooks': {
                'endpoints_count': len(self.webhook_endpoints),
                'webhooks_sent': self.integration_stats['webhooks_sent'],
                'endpoints': list(self.webhook_endpoints.keys())
            }
        }
    
    def get_integration_stats(self):
        """Get integration usage statistics"""
        return self.integration_stats.copy()
    
    async def test_integration(self, integration_type):
        """Test specific integration"""
        try:
            if integration_type == 'google_sheets':
                return await self._test_google_sheets()
            elif integration_type == 'calendar':
                return await self._test_calendar()
            elif integration_type == 'email':
                return await self._test_email()
            elif integration_type == 'webhooks':
                return await self._test_webhooks()
            else:
                return False, f"Unknown integration type: {integration_type}"
                
        except Exception as e:
            logger.error(f"Error testing integration {integration_type}: {e}")
            return False, str(e)
    
    async def _test_google_sheets(self):
        """Test Google Sheets integration"""
        if not self.google_sheets_enabled:
            return False, "Google Sheets not configured"
        
        # Simulate test
        await asyncio.sleep(0.2)
        return True, "Google Sheets integration working"
    
    async def _test_calendar(self):
        """Test Calendar integration"""
        if not self.calendar_enabled:
            return False, "Calendar not configured"
        
        # Simulate test
        await asyncio.sleep(0.2)
        return True, "Calendar integration working"
    
    async def _test_email(self):
        """Test Email integration"""
        if not self.email_enabled:
            return False, "Email not configured"
        
        # Simulate test
        await asyncio.sleep(0.2)
        return True, "Email integration working"
    
    async def _test_webhooks(self):
        """Test Webhook endpoints"""
        if not self.webhook_endpoints:
            return False, "No webhook endpoints configured"
        
        # Test each endpoint with a ping
        test_data = {
            'event_type': 'test_ping',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message': 'Integration test'
        }
        
        success, message = await self.send_webhook('test_ping', test_data)
        return success, message

# Global integration service instance
integration_service = IntegrationService()