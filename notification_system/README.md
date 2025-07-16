# Notification System MVP

## Overview
A scalable notification system that supports multiple delivery channels (email, SMS, push notifications, in-app) with features like templating, batching, rate limiting, and delivery tracking. This MVP demonstrates reliable message delivery across different platforms.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for metadata, Redis for queuing
- **Message Queue**: Redis/RabbitMQ for async processing
- **Email**: SMTP (SendGrid, AWS SES)
- **SMS**: Twilio API
- **Push**: Firebase Cloud Messaging (FCM)
- **Templates**: Go templates

## Key Features

### Core Functionality
- [ ] Multi-channel delivery (email, SMS, push, in-app)
- [ ] Template management and rendering
- [ ] User preference management
- [ ] Delivery scheduling and batching
- [ ] Rate limiting per channel
- [ ] Delivery tracking and status
- [ ] Retry mechanism with exponential backoff
- [ ] Analytics and reporting

### API Endpoints
- `POST /notifications/send` - Send notification
- `POST /notifications/bulk` - Send bulk notifications
- `GET /notifications/{id}/status` - Get delivery status
- `POST /templates` - Create notification template
- `GET /templates` - List templates
- `POST /users/{id}/preferences` - Update user preferences
- `GET /analytics/delivery` - Get delivery analytics

## Architecture Components

### 1. Notification Service
- Receives notification requests
- Validates and queues messages
- Handles template rendering

### 2. Channel Handlers
- Email handler (SMTP)
- SMS handler (Twilio)
- Push notification handler (FCM)
- In-app notification handler

### 3. Queue Manager
- Manages message queues per channel
- Implements priority queuing
- Handles retry logic

### 4. Template Engine
- Renders notification templates
- Supports dynamic content
- Multi-language support

## Database Schema

### Users Table
```sql
- id (UUID)
- email (string)
- phone (string)
- device_tokens (json) -- FCM tokens
- timezone (string)
- created_at (timestamp)
```

### User Preferences Table
```sql
- id (UUID)
- user_id (UUID)
- channel (enum: email, sms, push, in_app)
- enabled (boolean)
- quiet_hours_start (time)
- quiet_hours_end (time)
- frequency_limit (int) -- max per day
- created_at (timestamp)
- updated_at (timestamp)
```

### Templates Table
```sql
- id (UUID)
- name (string)
- subject (string)
- body (text)
- channel (enum: email, sms, push, in_app)
- language (string)
- variables (json) -- expected template variables
- is_active (boolean)
- created_at (timestamp)
- updated_at (timestamp)
```

### Notifications Table
```sql
- id (UUID)
- user_id (UUID)
- template_id (UUID)
- channel (enum: email, sms, push, in_app)
- subject (string)
- content (text)
- data (json) -- template variables
- status (enum: pending, sent, delivered, failed, read)
- scheduled_at (timestamp)
- sent_at (timestamp)
- delivered_at (timestamp)
- read_at (timestamp)
- retry_count (int)
- error_message (text)
- created_at (timestamp)
```

### Delivery Logs Table
```sql
- id (UUID)
- notification_id (UUID)
- channel (string)
- status (string)
- response_data (json)
- attempt_number (int)
- timestamp (timestamp)
```

## Notification Types

### 1. Immediate Notifications
- Real-time delivery
- High priority messages
- User actions, alerts

### 2. Scheduled Notifications
- Time-based delivery
- User timezone consideration
- Reminders, appointments

### 3. Batch Notifications
- Grouped delivery
- Digest emails
- Daily/weekly summaries

## Channel Implementations

### Email Channel
```go
type EmailChannel struct {
    SMTPHost     string
    SMTPPort     int
    Username     string
    Password     string
    FromAddress  string
    Templates    map[string]*template.Template
}
```

### SMS Channel
```go
type SMSChannel struct {
    TwilioSID     string
    TwilioToken   string
    FromNumber    string
    RateLimit     int // messages per minute
}
```

### Push Channel
```go
type PushChannel struct {
    FCMServerKey  string
    ProjectID     string
    BatchSize     int
}
```

## Template System

### Template Structure
```go
type Template struct {
    ID        string
    Name      string
    Subject   string
    Body      string
    Channel   ChannelType
    Variables []string
    Language  string
}
```

### Template Example
```yaml
name: "welcome_email"
subject: "Welcome to {{.AppName}}, {{.UserName}}!"
body: |
  Hi {{.UserName}},
  
  Welcome to {{.AppName}}! We're excited to have you on board.
  
  Your account has been created with email: {{.UserEmail}}
  
  Best regards,
  The {{.AppName}} Team
variables:
  - AppName
  - UserName
  - UserEmail
```

## Rate Limiting

### Per-Channel Limits
- Email: 100 messages/minute per user
- SMS: 10 messages/minute per user  
- Push: 50 messages/minute per user
- In-app: No limit (stored for later retrieval)

### Global Limits
- Total notifications per user per day
- Burst limits for high-priority messages
- Channel-specific daily quotas

## Retry Strategy

### Exponential Backoff
```go
type RetryConfig struct {
    MaxRetries      int
    InitialDelay    time.Duration
    MaxDelay        time.Duration
    BackoffFactor   float64
    JitterEnabled   bool
}

// Default: 1s, 2s, 4s, 8s, 16s (max 5 retries)
```

### Failure Handling
- Temporary failures: Retry with backoff
- Permanent failures: Mark as failed, no retry
- Channel-specific error handling

## Queue Management

### Queue Structure
```go
type NotificationQueue struct {
    Channel     ChannelType
    Priority    Priority
    Capacity    int
    Workers     int
    RateLimit   int
}
```

### Priority Levels
- `CRITICAL`: Immediate processing
- `HIGH`: Within 1 minute
- `NORMAL`: Within 5 minutes
- `LOW`: Within 30 minutes

## Analytics and Metrics

### Delivery Metrics
- Delivery rate by channel
- Average delivery time
- Failure rates and reasons
- User engagement metrics

### Performance Metrics
- Queue processing time
- Template rendering performance
- API response times
- System throughput

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL and Redis
4. Configure external service credentials:
   - SMTP settings for email
   - Twilio credentials for SMS
   - FCM server key for push notifications
5. Run database migrations
6. Start the queue workers
7. Start the main server: `go run main.go`

## Configuration Example

```yaml
# config.yaml
database:
  host: localhost
  port: 5432
  dbname: notifications
  
redis:
  host: localhost
  port: 6379
  
channels:
  email:
    smtp_host: smtp.sendgrid.net
    smtp_port: 587
    username: apikey
    password: ${SENDGRID_API_KEY}
    
  sms:
    twilio_sid: ${TWILIO_SID}
    twilio_token: ${TWILIO_TOKEN}
    from_number: "+1234567890"
    
  push:
    fcm_server_key: ${FCM_SERVER_KEY}
    project_id: "your-firebase-project"

rate_limits:
  email: 100  # per minute
  sms: 10     # per minute
  push: 50    # per minute
```

## API Usage Examples

### Send Single Notification
```bash
curl -X POST "http://localhost:8080/notifications/send" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "template_id": "welcome_email",
    "channel": "email",
    "data": {
      "UserName": "John Doe",
      "AppName": "MyApp",
      "UserEmail": "john@example.com"
    }
  }'
```

### Send Bulk Notifications
```bash
curl -X POST "http://localhost:8080/notifications/bulk" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "newsletter",
    "channel": "email",
    "users": ["user1", "user2", "user3"],
    "data": {
      "NewsletterTitle": "Weekly Update",
      "Content": "This week in tech..."
    }
  }'
```

## Future Enhancements
- Advanced template editor UI
- A/B testing for notification content
- Machine learning for optimal delivery timing
- Rich media support (images, videos)
- Interactive notifications (buttons, actions)
- Webhook support for delivery status
- Advanced segmentation and targeting
- Multi-tenancy support 