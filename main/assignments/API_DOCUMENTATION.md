# Assignments API Documentation

## Overview
The Assignments API provides endpoints for managing assignments and submissions with role-based access control.

## Authentication
All endpoints require JWT authentication. Include the token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

## User Roles and Permissions

### Admin/Principal
- Full access to all assignments and submissions
- Can create, read, update, delete any assignment or submission
- Can grade any submission

### Teacher
- Can create assignments for their subjects/sections
- Can view and modify their own assignments
- Can view and grade submissions for their assignments
- Cannot access other teachers' assignments or submissions

### Student
- Can view published assignments for their enrolled sections
- Can create submissions for assignments
- Can view and update their own ungraded submissions
- Cannot access other students' submissions

## Endpoints

### Assignments

#### GET /api/assignments/
List assignments based on user role.

**Permissions:** Students, Teachers, Admin, Principal

**Response:**
```json
[
    {
        "id": "uuid",
        "title": "Math Assignment 1",
        "subject": "uuid",
        "subject_name": "Mathematics",
        "section": "uuid", 
        "section_name": "Grade 10-A",
        "teacher": "uuid",
        "teacher_name": "John Doe",
        "content_type": "text",
        "text_content": "Solve problems 1-10",
        "file_content": null,
        "url_content": null,
        "max_score": 100.0,
        "due_date": "2024-01-15T23:59:59Z",
        "is_published": true,
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-01T10:00:00Z"
    }
]
```

#### POST /api/assignments/
Create a new assignment.

**Permissions:** Teachers, Admin, Principal

**Request Body:**
```json
{
    "title": "Math Assignment 1",
    "subject": "uuid",
    "section": "uuid",
    "content_type": "text",
    "text_content": "Solve problems 1-10",
    "max_score": 100.0,
    "due_date": "2024-01-15T23:59:59Z",
    "is_published": true
}
```

#### GET /api/assignments/{id}/
Retrieve a specific assignment.

**Permissions:** Students, Teachers, Admin, Principal (with filtering)

#### PUT/PATCH /api/assignments/{id}/
Update an assignment.

**Permissions:** Teachers (own assignments), Admin, Principal

#### DELETE /api/assignments/{id}/
Delete an assignment.

**Permissions:** Teachers (own assignments), Admin, Principal

#### GET /api/assignments/{id}/submissions/
Get all submissions for an assignment.

**Permissions:** Students (own submission only), Teachers (their assignments), Admin, Principal

### Submissions

#### GET /api/submissions/
List submissions based on user role.

**Permissions:** Students, Teachers, Admin, Principal

**Response:**
```json
[
    {
        "id": "uuid",
        "assignment": "uuid",
        "assignment_title": "Math Assignment 1",
        "student": "uuid",
        "student_name": "Jane Smith",
        "submission_file": "/media/assignments/submissions/file.pdf",
        "submission_text": "My solution...",
        "submission_url": null,
        "status": "submitted",
        "score": null,
        "max_score": 100.0,
        "feedback": null,
        "submitted_at": "2024-01-10T14:30:00Z",
        "graded_at": null
    }
]
```

#### POST /api/submissions/
Create a new submission.

**Permissions:** Students only

**Request Body:**
```json
{
    "assignment": "uuid",
    "submission_text": "My solution to the assignment",
    "submission_file": "file_upload"
}
```

#### GET /api/submissions/{id}/
Retrieve a specific submission.

**Permissions:** Students (own), Teachers (their assignments), Admin, Principal

#### PUT/PATCH /api/submissions/{id}/
Update a submission.

**Permissions:** Students (own ungraded), Teachers (grading), Admin, Principal

#### DELETE /api/submissions/{id}/
Delete a submission.

**Permissions:** Admin, Principal only

#### PATCH /api/submissions/{id}/grade/
Grade a submission.

**Permissions:** Teachers (their assignments), Admin, Principal

**Request Body:**
```json
{
    "score": 85.0,
    "feedback": "Good work! Minor errors in problem 3.",
    "status": "graded"
}
```

## Error Responses

### 401 Unauthorized
```json
{
    "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
    "error": "Only teachers can create assignments"
}
```

### 404 Not Found
```json
{
    "detail": "Not found."
}
```

### 400 Bad Request
```json
{
    "field_name": ["This field is required."]
}
```

## Status Codes
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 500: Internal Server Error