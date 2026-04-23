from rest_framework import serializers
from django.utils import timezone
from .models import Quiz, Question, Choice, QuizAttempt, QuizAnswer
from .models import QuizFilterPreference
from shared.serializers import SanitizedModelSerializer


class ChoiceSerializer(SanitizedModelSerializer):
    sanitize_fields = ('choice_text',)
    class Meta:
        model = Choice
        fields = ['id', 'choice_text', 'is_correct']
        read_only_fields = ['id']


class QuestionSerializer(SanitizedModelSerializer):
    sanitize_fields = ('question_text',)
    choices = ChoiceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Question
        fields = ['id', 'quiz', 'question_text', 'question_type', 'points', 'choices']
        read_only_fields = ['id']


class QuizSerializer(SanitizedModelSerializer):
    sanitize_fields = ('title', 'description')
    subject_name = serializers.CharField(source='section_subject.subject.name', read_only=True)
    section_name = serializers.CharField(source='section_subject.section.name', read_only=True)
    subject_id = serializers.CharField(source='section_subject.subject.id', read_only=True)
    section_id = serializers.CharField(source='section_subject.section.id', read_only=True)
    questions = QuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            'id', 'section_subject', 'section_id', 'section_name', 'subject_id', 'subject_name',
            'title', 'description', 'total_points', 'time_limit_minutes',
            'attempt_limit', 'due_date', 'ai_grade_on_submit', 'security_level', 'is_available',
            'questions', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate_due_date(self, value):
        if value and value < timezone.now():
            raise serializers.ValidationError('Due date cannot be in the past.')
        return value


class QuizAnswerSerializer(SanitizedModelSerializer):
    sanitize_fields = ('text_answer',)
    selected_choice_text = serializers.CharField(source='selected_choice.choice_text', read_only=True)
    selected_choice_is_correct = serializers.BooleanField(source='selected_choice.is_correct', read_only=True)
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_points = serializers.FloatField(source='question.points', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    class Meta:
        model = QuizAnswer
        fields = [
            'id', 'question', 'question_text', 'question_type', 'question_points',
            'selected_choice', 'selected_choice_text', 'selected_choice_is_correct',
            'text_answer', 'points_earned', 'is_correct', 'feedback'
        ]
        read_only_fields = ['id', 'points_earned', 'is_correct']


class QuizAttemptSerializer(serializers.ModelSerializer):
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    section_subject_id = serializers.CharField(source='quiz.section_subject.id', read_only=True)
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    answers = QuizAnswerSerializer(many=True, read_only=True)
    
    class Meta:
        model = QuizAttempt
        fields = [
            'id', 'quiz', 'quiz_title', 'section_subject_id', 'student', 'student_name',
            'score', 'raw_score', 'penalty_percent', 'feedback', 'ai_grade_applied', 'ai_grade_failed',
            'answers', 'started_at', 'submitted_at'
        ]
        read_only_fields = ['id', 'started_at', 'submitted_at']


class QuizFilterPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizFilterPreference
        fields = ['id', 'quiz', 'submitted_only', 'needs_manual_only', 'score_only', 'feedback_only', 'updated_at']
        read_only_fields = ['id', 'updated_at']
