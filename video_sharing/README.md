# Video Sharing Platform MVP

## Overview
A video sharing platform similar to YouTube that allows users to upload, stream, and manage video content. This MVP demonstrates video processing, streaming, metadata management, and basic social features.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for metadata, AWS S3/MinIO for video storage
- **Video Processing**: FFmpeg for transcoding
- **Streaming**: HLS (HTTP Live Streaming)
- **CDN**: CloudFront or similar for video delivery
- **Queue**: Redis for async video processing

## Key Features

### Core Functionality
- [ ] User authentication and channels
- [ ] Video upload and processing
- [ ] Multiple quality streaming (240p, 480p, 720p, 1080p)
- [ ] Video metadata management
- [ ] Like/dislike and comment system
- [ ] Video search and discovery
- [ ] Subscription system
- [ ] Basic analytics and view tracking

### API Endpoints
- `POST /auth/login` - User authentication
- `POST /auth/register` - User registration
- `POST /videos/upload` - Upload video
- `GET /videos/{id}` - Get video details
- `GET /videos/{id}/stream/{quality}` - Stream video
- `GET /videos` - List/search videos
- `POST /videos/{id}/like` - Like/unlike video
- `POST /videos/{id}/comments` - Add comment
- `POST /channels/{id}/subscribe` - Subscribe to channel

## Architecture Components

### 1. Video Upload Service
- Handles multipart file uploads
- Validates video formats and size
- Queues videos for processing

### 2. Video Processing Service
- Transcodes videos to multiple qualities
- Generates thumbnails
- Creates HLS segments for streaming

### 3. Streaming Service
- Serves video content via HLS
- Handles adaptive bitrate streaming
- Manages CDN integration

### 4. Metadata Service
- Manages video information
- Handles search indexing
- Tracks view counts and engagement

## Database Schema

### Users Table
```sql
- id (UUID)
- username (string)
- email (string)
- password_hash (string)
- channel_name (string)
- avatar_url (string)
- subscriber_count (int)
- created_at (timestamp)
```

### Videos Table
```sql
- id (UUID)
- title (string)
- description (text)
- uploader_id (UUID)
- duration (int) -- seconds
- file_size (bigint)
- thumbnail_url (string)
- view_count (bigint)
- like_count (int)
- dislike_count (int)
- status (enum: processing, ready, failed)
- privacy (enum: public, unlisted, private)
- created_at (timestamp)
- updated_at (timestamp)
```

### Video Files Table
```sql
- id (UUID)
- video_id (UUID)
- quality (string) -- 240p, 480p, 720p, 1080p
- format (string) -- mp4, hls
- file_path (string)
- file_size (bigint)
- bitrate (int)
```

### Comments Table
```sql
- id (UUID)
- video_id (UUID)
- user_id (UUID)
- content (text)
- like_count (int)
- parent_comment_id (UUID, nullable)
- created_at (timestamp)
```

### Subscriptions Table
```sql
- id (UUID)
- subscriber_id (UUID)
- channel_id (UUID)
- created_at (timestamp)
```

### Video Likes Table
```sql
- id (UUID)
- video_id (UUID)
- user_id (UUID)
- is_like (boolean) -- true for like, false for dislike
- created_at (timestamp)
```

## Video Processing Pipeline

### 1. Upload Phase
- Accept video upload
- Validate file format and size
- Store original file in temporary storage
- Queue for processing

### 2. Processing Phase
- Extract video metadata (duration, resolution, etc.)
- Generate thumbnail images
- Transcode to multiple qualities
- Create HLS segments
- Store processed files in permanent storage

### 3. Publishing Phase
- Update video status to "ready"
- Index video for search
- Send notifications to subscribers

## Streaming Architecture

### HLS (HTTP Live Streaming)
- Segment videos into small chunks (10 seconds each)
- Create manifest files (.m3u8) for each quality
- Enable adaptive bitrate streaming
- Support for seeking and progressive download

### CDN Integration
- Distribute video content globally
- Cache popular content at edge locations
- Reduce latency and bandwidth costs

## Storage Strategy
- Original uploads: Temporary storage (auto-delete after processing)
- Processed videos: Permanent storage with lifecycle policies
- Thumbnails: Separate storage bucket with fast access
- User uploads: Organized by user ID and upload date

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Install FFmpeg for video processing
4. Set up PostgreSQL and Redis
5. Configure AWS S3 or MinIO for storage
6. Set up environment variables
7. Run database migrations
8. Start the video processing worker
9. Start the main server: `go run main.go`

## Processing Requirements

### FFmpeg Installation
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### Video Processing Commands
```bash
# Transcode to different qualities
ffmpeg -i input.mp4 -vf scale=1280:720 -c:v libx264 -c:a aac output_720p.mp4

# Generate HLS segments
ffmpeg -i input.mp4 -c:v libx264 -c:a aac -f hls -hls_time 10 -hls_playlist_type vod output.m3u8

# Generate thumbnail
ffmpeg -i input.mp4 -ss 00:00:01 -vframes 1 -q:v 2 thumbnail.jpg
```

## Future Enhancements
- Live streaming capabilities
- Advanced recommendation engine
- Content monetization features
- Advanced analytics dashboard
- Content moderation and copyright detection
- Mobile app support
- Real-time chat for live streams
- Collaborative playlists 