# E-Learning Backend API Documentation

## Overview
Complete REST API for the E-Learning Management System with role-based access control.

## Authentication
All endpoints require JWT authentication:
```
Authorization: Bearer <your_jwt_token>
```

## User Roles & Permissions

### Admin/Principal/Dean
- Full access to all resources
- Can create, read, update, delete any data
- User management capabilities

### Teacher
- Can manage their own assignments, learning_materials, quizzes
- Can view and grade submissions for their subjects
- Can view students in their sections
- Cannot access other teachers' data

### Student
- Can view published content for enrolled sections
- Can submit assignments and quizzes
- Can view their own grades and submissions
- Cannot access other students' data

## Data Models
This section documents all Django models in the backend and their key fields, relationships, and constraints.

### CustomUser
Custom authentication user model with role-specific fields.
- Table: `user_customuser`
- Primary key: `id` (UUID)
- Key fields: `first_name`, `last_name`, `middle_name`, `email`, `role`, `student_id`, `employee_id`, `phone_number`, `address`, `date_of_birth`, `profile_picture`, `is_active`, `is_staff`, `date_joined`, `updated_at`
- Role choices: `student`, `teacher`, `principal`, `dean`, `admin`
- Constraints: `email` unique; `student_id` unique (nullable); `employee_id` unique (nullable)
- Indexes: `role + is_active`, `student_id`, `employee_id`
- Notes: `email` is the username field

### School_levels
Top-level grouping for departments (e.g., Elementary, SHS, College).
- Table: `school_levels_school_levels`
- Primary key: `id` (UUID)
- Key fields: `name`, `description`, `created_at`
- Constraints: `name` unique
- Ordering: `name`

### Department
Department within a school level.
- Table: `departments_department`
- Primary key: `id` (UUID)
- Key fields: `name`, `code`, `description`, `school_level`, `principal_or_dean`, `created_at`, `updated_at`
- Relationships: `school_level` -> `School_levels` (FK, cascade), `principal_or_dean` -> `CustomUser` (FK, set null; role in `principal|dean|admin`)
- Constraints: `name` unique; `code` unique
- Indexes: `school_level + name`

### GradeLevel
Grade levels within a department.
- Table: `year_levels_year_levels`
- Primary key: `id` (UUID)
- Key fields: `name`, `level_number`, `department`, `description`, `created_at`
- Relationships: `department` -> `Department` (FK, cascade)
- Constraints: `name` unique; `level_number` unique
- Indexes: `department + level_number`
- Ordering: `level_number`

### Program_or_Strand
Programs/strands (especially for SHS/College).
- Table: `programs_program_or_strand`
- Primary key: `id` (UUID)
- Key fields: `code`, `name`, `department`, `duration_years`, `description`, `created_at`
- Relationships: `department` -> `Department` (FK, cascade)
- Constraints: `code` unique
- Indexes: `department + code`
- Ordering: `department + name`

### Section
A class section (e.g., Grade 10 - A) within a grade level and school year.
- Table: `sections_section`
- Primary key: `id` (UUID)
- Key fields: `name`, `grade_level`, `program_or_course`, `adviser`, `school_year`, `max_students`, `description`, `created_at`
- Relationships: `grade_level` -> `GradeLevel` (FK, cascade), `program_or_course` -> `Program_or_Strand` (FK, cascade), `adviser` -> `CustomUser` (FK, set null; role `teacher`)
- Constraints: unique together `name + grade_level + school_year`
- Indexes: `grade_level + school_year`
- Ordering: `grade_level + name`

### Enrollment
Tracks a student’s enrollment in a section.
- Table: `sections_enrollment`
- Primary key: `id` (UUID)
- Key fields: `student`, `section`, `status`, `enrolled_at`, `dropped_at`, `completed_at`
- Status choices: `active`, `dropped`, `completed`
- Relationships: `student` -> `CustomUser` (FK, cascade; role `student`), `section` -> `Section` (FK, cascade)
- Constraints: unique together `student + section`
- Indexes: `student + status`, `section + status`
- Ordering: `-enrolled_at`

### Subject
Academic subject tied to department, grade, and section.
- Table: `subjects_subject`
- Primary key: `id` (UUID)
- Key fields: `name`, `code`, `department`, `grade_level`, `section`, `teacher`, `units`, `description`, `created_at`
- Relationships: `department` -> `Department` (FK, cascade), `grade_level` -> `GradeLevel` (FK, cascade), `section` -> `Section` (FK, cascade), `teacher` -> `CustomUser` (FK, set null; role `teacher`)
- Constraints: unique together `code + section`
- Indexes: `section + teacher`, `grade_level + section`
- Ordering: `grade_level + name`

### StudentGrade
Overall grade for a student per subject and grading period.
- Table: `subjects_studentgrade`
- Primary key: `id` (UUID)
- Key fields: `student`, `subject`, `grading_period`, `grade`, `remarks`, `created_at`, `updated_at`
- Grading period choices: `1st`, `2nd`, `3rd`, `4th`, `midterm`, `final`
- Relationships: `student` -> `CustomUser` (FK, cascade; role `student`), `subject` -> `Subject` (FK, cascade)
- Constraints: unique together `student + subject + grading_period`
- Indexes: `student + subject`, `subject + grading_period`
- Ordering: `subject + grading_period + student`
- Validation: `grade` between 0 and 100

### Learning Material
Learning material for a subject.
- Table: `learning_materials_lesson`
- Primary key: `id` (UUID)
- Key fields: `title`, `subject`, `teacher`, `content_type`, `text_content`, `file_content`, `url_content`, `order`, `is_published`, `created_at`, `updated_at`
- Content type choices: `pdf`, `text`, `link`, `video`
- Relationships: `subject` -> `Subject` (FK, cascade), `teacher` -> `CustomUser` (FK, set null; role `teacher`)
- Indexes: `subject + is_published`, `subject + order`
- Ordering: `subject + order + created_at`

### Assignment
Assignments linked to a subject and section.
- Table: `assignments_assignment`
- Primary key: `id` (UUID)
- Key fields: `title`, `subject`, `section`, `teacher`, `content_type`, `text_content`, `file_content`, `url_content`, `max_score`, `due_date`, `is_published`, `created_at`, `updated_at`
- Content type choices: `pdf`, `text`, `link`, `video`
- Relationships: `subject` -> `Subject` (FK, cascade), `section` -> `Section` (FK, cascade), `teacher` -> `CustomUser` (FK, set null; role `teacher`)
- Indexes: `subject + section`, `due_date + is_published`
- Ordering: `due_date`
- Validation: `max_score` >= 0

### AssignmentSubmission
Student submissions for assignments.
- Table: `assignments_assignmentsubmission`
- Primary key: `id` (UUID)
- Key fields: `assignment`, `student`, `submission_file`, `submission_text`, `submission_url`, `status`, `score`, `feedback`, `submitted_at`, `graded_at`
- Status choices: `submitted`, `graded`, `late`
- Relationships: `assignment` -> `Assignment` (FK, cascade), `student` -> `CustomUser` (FK, cascade; role `student`)
- Constraints: unique together `assignment + student`
- Indexes: `assignment + student`, `student + status`
- Ordering: `-submitted_at`
- Validation: `score` >= 0

### Quiz
Quizzes tied to subject and section.
- Table: `quizzes_quiz`
- Primary key: `id` (UUID)
- Key fields: `title`, `subject`, `section`, `teacher`, `description`, `time_limit`, `max_attempts`, `is_published`, `due_date`, `created_at`, `updated_at`
- Relationships: `subject` -> `Subject` (FK, cascade), `section` -> `Section` (FK, cascade), `teacher` -> `CustomUser` (FK, set null; role `teacher`)
- Indexes: `subject + section`, `due_date + is_published`
- Ordering: `due_date`

### Question
Questions that belong to a quiz.
- Table: `quizzes_question`
- Primary key: `id` (UUID)
- Key fields: `quiz`, `text`, `question_type`, `marks`, `order`
- Question type choices: `mcq`, `tf`, `essay`, `file`
- Relationships: `quiz` -> `Quiz` (FK, cascade)
- Indexes: `quiz + order`
- Ordering: `quiz + order`
- Validation: `marks` >= 0

### Choice
Multiple-choice options for a question.
- Table: `quizzes_choice`
- Primary key: `id` (UUID)
- Key fields: `question`, `text`, `is_correct`, `order`
- Relationships: `question` -> `Question` (FK, cascade)
- Ordering: `question + order`

### QuizSubmission
Student attempts for a quiz.
- Table: `quizzes_quizsubmission`
- Primary key: `id` (UUID)
- Key fields: `quiz`, `student`, `attempt_number`, `status`, `total_score`, `started_at`, `submitted_at`
- Status choices: `in_progress`, `submitted`, `graded`
- Relationships: `quiz` -> `Quiz` (FK, cascade), `student` -> `CustomUser` (FK, cascade; role `student`)
- Indexes: `quiz + student`, `student + status`
- Ordering: `-started_at`
- Validation: `total_score` >= 0

### QuizAnswer
Answers for each quiz submission and question.
- Table: `quizzes_quizanswer`
- Primary key: `id` (UUID)
- Key fields: `submission`, `question`, `selected_choice`, `text_answer`, `file_answer`, `marks_obtained`, `is_correct`
- Relationships: `submission` -> `QuizSubmission` (FK, cascade), `question` -> `Question` (FK, cascade), `selected_choice` -> `Choice` (FK, set null)
- Constraints: unique together `submission + question`
- Indexes: `submission + question`
- Validation: `marks_obtained` >= 0

### Chat
Chat threads between users.
- Table: `announcements_chat`
- Primary key: `id` (UUID)
- Key fields: `participants`, `created_at`, `updated_at`
- Relationships: `participants` -> `CustomUser` (M2M)
- Ordering: `-updated_at`

### Message
Messages within a chat.
- Table: `announcements_message`
- Primary key: `id` (UUID)
- Key fields: `chat`, `sender`, `content`, `file`, `is_read`, `created_at`
- Relationships: `chat` -> `Chat` (FK, cascade), `sender` -> `CustomUser` (FK, cascade)
- Indexes: `chat + created_at`
- Ordering: `created_at`

## API Endpoints

### Authentication
- `POST /api/auth/login/token` - Login and get JWT token
- `POST /api/token/refresh/` - Refresh JWT token

### Users
- `GET /api/users/` - List users (Admin only)
- `POST /api/users/` - Create user (Admin only)
- `GET /api/users/{id}/` - Get user details (Own profile or Admin)
- `PUT/PATCH /api/users/{id}/` - Update user (Admin only)
- `DELETE /api/users/{id}/` - Delete user (Admin only)
- `GET /api/users/profile/` - Get current user profile
- `PATCH /api/users/update_profile/` - Update current user profile

### School Structure
- `GET/POST /api/school-levels/` - School levels (Read: All, Write: Admin)
- `GET/POST /api/departments/` - Departments (Read: All, Write: Admin)
- `GET/POST /api/programs/` - Programs/Strands (Read: All, Write: Admin)
- `GET/POST /api/grade-levels/` - Grade levels (Read: All, Write: Admin)

### Sections & Enrollment
- `GET/POST /api/sections/` - Sections (Read: All, Write: Admin)
- `GET /api/sections/{id}/enrollments/` - Section enrollments
- `GET/POST /api/enrollments/` - Enrollments (Read: All, Write: Admin)

### Subjects & Grades
- `GET /api/subjects/` - List subjects (filtered by role)
- `POST /api/subjects/` - Create subject (Teachers/Admin)
- `GET /api/subjects/{id}/grades/` - Subject grades
- `GET/POST /api/grades/` - Student grades (Teachers can create/update)

### Learning Materials
- `GET /api/learning_materials/` - List learning_materials (Students: published only)
- `POST /api/learning_materials/` - Create learning material (Teachers/Admin)
- `PUT/PATCH /api/learning_materials/{id}/` - Update learning material (Own learning_materials or Admin)
- `DELETE /api/learning_materials/{id}/` - Delete learning material (Own learning_materials or Admin)

### Assignments
- `GET /api/assignments/` - List assignments (filtered by role)
- `POST /api/assignments/` - Create assignment (Teachers/Admin)
- `GET /api/assignments/{id}/submissions/` - Assignment submissions
- `GET /api/submissions/` - List submissions (filtered by role)
- `POST /api/submissions/` - Create submission (Students only)
- `PATCH /api/submissions/{id}/grade/` - Grade submission (Teachers/Admin)

### Quizzes
- `GET /api/quizzes/` - List quizzes (filtered by role)
- `POST /api/quizzes/` - Create quiz (Teachers/Admin)
- `GET /api/quizzes/{id}/submissions/` - Quiz submissions
- `GET/POST /api/questions/` - Quiz questions (Teachers/Admin)
- `GET/POST /api/choices/` - Question choices (Teachers/Admin)
- `GET/POST /api/quiz-submissions/` - Quiz submissions
- `PATCH /api/quiz-submissions/{id}/submit/` - Submit quiz

## Data Filtering by Role

### Students
- See only published content for enrolled sections
- Can only access their own submissions and grades
- Cannot see other students' data

### Teachers
- See only their own created content (assignments, learning_materials, quizzes)
- Can access submissions/grades for their subjects
- Cannot access other teachers' content

### Admin/Principal
- Full access to all data
- No filtering applied

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
    "error": "Permission denied"
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

## Example Usage

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login/token \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'
```

### Get User Profile
```bash
curl -X GET http://localhost:8000/api/users/profile/ \
  -H "Authorization: Bearer <token>"
```

### Create Assignment (Teacher)
```bash
curl -X POST http://localhost:8000/api/assignments/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Math Assignment 1",
    "subject": "uuid",
    "section": "uuid",
    "content_type": "text",
    "text_content": "Solve problems 1-10",
    "max_score": 100.0,
    "due_date": "2024-01-15T23:59:59Z"
  }'
```

### Submit Assignment (Student)
```bash
curl -X POST http://localhost:8000/api/submissions/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "assignment": "uuid",
    "submission_text": "My solution..."
  }'
```
