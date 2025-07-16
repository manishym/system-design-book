# Chat System MVP

## Overview
A real-time chat system that supports one-on-one messaging, group chats, and basic user management. This MVP demonstrates core messaging functionality with WebSocket connections for real-time communication.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for user data, Redis for session management
- **Real-time**: WebSocket connections
- **Message Queue**: Redis/Go channels for message routing

## Key Features

### Core Functionality
- [ ] User registration and authentication
- [ ] One-on-one messaging
- [ ] Group chat creation and management
- [ ] Real-time message delivery via WebSockets
- [ ] Message persistence and history
- [ ] Online/offline user status

### API Endpoints
- `POST /auth/login` - User authentication
- `POST /auth/register` - User registration
- `GET /users` - List users
- `POST /chats` - Create new chat/group
- `GET /chats` - List user's chats
- `GET /chats/{id}/messages` - Get chat history
- `WS /ws` - WebSocket endpoint for real-time messaging

## Architecture Components

### 1. WebSocket Manager
- Maintains active connections
- Routes messages between users
- Handles connection lifecycle

### 2. Message Handler
- Processes incoming messages
- Stores messages in database
- Broadcasts to relevant users

### 3. User Service
- User authentication and management
- Online status tracking

## Database Schema

### Users Table
```sql
- id (UUID)
- username (string)
- email (string)
- password_hash (string)
- created_at (timestamp)
- last_seen (timestamp)
```

### Chats Table
```sql
- id (UUID)
- name (string, nullable for 1-on-1)
- type (enum: direct, group)
- created_by (UUID)
- created_at (timestamp)
```

### Messages Table
```sql
- id (UUID)
- chat_id (UUID)
- sender_id (UUID)
- content (text)
- message_type (enum: text, image, file)
- created_at (timestamp)
```

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL and Redis
4. Run database migrations
5. Start the server: `go run main.go`

## Future Enhancements
- File and image sharing
- Message encryption
- Push notifications
- Message search functionality
- Chat moderation features 