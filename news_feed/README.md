# News Feed MVP

## Overview
A social media news feed system that displays personalized content to users based on their connections and interests. This MVP demonstrates core feed generation, ranking algorithms, and real-time updates.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for relational data, Redis for caching
- **Message Queue**: Redis for async processing
- **Search**: Elasticsearch (optional for advanced search)

## Key Features

### Core Functionality
- [ ] User profiles and authentication
- [ ] Post creation (text, images)
- [ ] Follow/unfollow users
- [ ] Personalized news feed generation
- [ ] Feed ranking algorithm
- [ ] Like and comment system
- [ ] Real-time feed updates
- [ ] Content caching for performance

### API Endpoints
- `POST /auth/login` - User authentication
- `POST /auth/register` - User registration
- `GET /users/{id}` - Get user profile
- `POST /users/{id}/follow` - Follow user
- `POST /posts` - Create new post
- `GET /feed` - Get personalized feed
- `GET /posts/{id}` - Get specific post
- `POST /posts/{id}/like` - Like/unlike post
- `POST /posts/{id}/comments` - Add comment

## Architecture Components

### 1. Feed Generator
- Creates personalized feeds for users
- Implements ranking algorithms
- Handles feed caching strategies

### 2. Post Service
- Manages post creation and retrieval
- Handles media upload and processing
- Manages post metadata

### 3. Social Graph Service
- Manages follow/follower relationships
- Calculates user connections
- Handles friend suggestions

### 4. Ranking Engine
- Scores posts based on multiple factors
- Considers user preferences and engagement
- Updates scores in real-time

## Database Schema

### Users Table
```sql
- id (UUID)
- username (string)
- email (string)
- password_hash (string)
- bio (text)
- avatar_url (string)
- followers_count (int)
- following_count (int)
- created_at (timestamp)
```

### Posts Table
```sql
- id (UUID)
- author_id (UUID)
- content (text)
- media_urls (json)
- likes_count (int)
- comments_count (int)
- engagement_score (float)
- created_at (timestamp)
- updated_at (timestamp)
```

### Follows Table
```sql
- id (UUID)
- follower_id (UUID)
- followed_id (UUID)
- created_at (timestamp)
```

### Likes Table
```sql
- id (UUID)
- user_id (UUID)
- post_id (UUID)
- created_at (timestamp)
```

### Comments Table
```sql
- id (UUID)
- post_id (UUID)
- author_id (UUID)
- content (text)
- created_at (timestamp)
```

## Feed Generation Strategies

### 1. Pull Model (On-demand)
- Generate feed when user requests it
- Query posts from followed users
- Apply ranking algorithm

### 2. Push Model (Pre-computed)
- Pre-generate feeds for active users
- Update feeds when new posts are created
- Store in cache for fast retrieval

### 3. Hybrid Model
- Combine both approaches
- Use push for popular users
- Use pull for less active users

## Ranking Algorithm Factors
- Recency of post
- User engagement (likes, comments, shares)
- Relationship strength with author
- Content type preferences
- User activity patterns

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL and Redis
4. Run database migrations
5. Start the server: `go run main.go`
6. Optionally set up Elasticsearch for search

## Future Enhancements
- Machine learning-based ranking
- Story/temporary posts feature
- Advanced content filtering
- Trending topics detection
- Push notifications for feed updates
- Content recommendation engine 