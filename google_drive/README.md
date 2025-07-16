# Google Drive Clone MVP

## Overview
A cloud storage service that allows users to upload, organize, share, and manage files. This MVP demonstrates core file storage functionality with a RESTful API and basic file management features.

## Technology Stack
- **Backend**: Go (Golang)
- **Database**: PostgreSQL for metadata, AWS S3/MinIO for file storage
- **Authentication**: JWT tokens
- **File Processing**: Go standard library

## Key Features

### Core Functionality
- [ ] User authentication and authorization
- [ ] File upload and download
- [ ] Folder creation and organization
- [ ] File and folder sharing with permissions
- [ ] File versioning (basic)
- [ ] Search functionality
- [ ] Storage quota management

### API Endpoints
- `POST /auth/login` - User authentication
- `POST /auth/register` - User registration
- `POST /files/upload` - Upload files
- `GET /files/{id}/download` - Download files
- `GET /files` - List user's files and folders
- `POST /folders` - Create folder
- `PUT /files/{id}/move` - Move file/folder
- `POST /files/{id}/share` - Share file/folder
- `GET /files/search?q={query}` - Search files

## Architecture Components

### 1. File Service
- Handles file upload/download operations
- Manages file metadata
- Interfaces with storage backend (S3/MinIO)

### 2. Folder Service
- Manages folder hierarchy
- Handles move/copy operations

### 3. Permission Service
- Manages file/folder sharing
- Controls access permissions

### 4. Storage Service
- Abstracts storage backend operations
- Handles file chunking for large uploads

## Database Schema

### Users Table
```sql
- id (UUID)
- email (string)
- password_hash (string)
- storage_used (bigint)
- storage_limit (bigint)
- created_at (timestamp)
```

### Files Table
```sql
- id (UUID)
- name (string)
- path (string)
- size (bigint)
- mime_type (string)
- storage_key (string)
- owner_id (UUID)
- parent_folder_id (UUID, nullable)
- version (int)
- created_at (timestamp)
- updated_at (timestamp)
```

### Folders Table
```sql
- id (UUID)
- name (string)
- path (string)
- owner_id (UUID)
- parent_folder_id (UUID, nullable)
- created_at (timestamp)
```

### Permissions Table
```sql
- id (UUID)
- resource_id (UUID)
- resource_type (enum: file, folder)
- user_id (UUID)
- permission_type (enum: read, write, admin)
- granted_by (UUID)
- created_at (timestamp)
```

## File Storage Strategy
- Use content-based deduplication
- Implement chunked uploads for large files
- Store metadata in PostgreSQL
- Store actual files in S3-compatible storage

## Getting Started

1. Clone the repository
2. Install Go dependencies: `go mod tidy`
3. Set up PostgreSQL database
4. Configure S3/MinIO storage
5. Set environment variables for storage credentials
6. Run database migrations
7. Start the server: `go run main.go`

## Future Enhancements
- Real-time collaboration features
- Advanced file versioning
- Thumbnail generation for images
- File preview functionality
- Trash/recycle bin
- Activity logs and audit trails 