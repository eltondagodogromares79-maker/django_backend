# Generated manually because DB not available for makemigrations
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('sections', '0007_enrollment_is_current'),
        ('users', '0007_alter_customuser_profile_picture'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatRoom',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('room_key', models.CharField(max_length=255, unique=True)),
                ('room_type', models.CharField(choices=[('section', 'Section'), ('direct', 'Direct'), ('group', 'Group')], max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_chat_rooms', to=settings.AUTH_USER_MODEL)),
                ('section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chat_rooms', to='sections.section')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('content', models.TextField()),
                ('kind', models.CharField(choices=[('text', 'Text'), ('image', 'Image'), ('file', 'File'), ('audio', 'Audio'), ('video', 'Video')], default='text', max_length=20)),
                ('sent_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='chat.chatroom')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['sent_at'],
            },
        ),
        migrations.CreateModel(
            name='ChatRoomMember',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='chat.chatroom')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('room', 'user')},
            },
        ),
        migrations.CreateModel(
            name='ChatReadReceipt',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('last_read_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='read_receipts', to='chat.chatroom')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_read_receipts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('room', 'user')},
            },
        ),
        migrations.AddIndex(
            model_name='chatroom',
            index=models.Index(fields=['room_type', 'room_key'], name='chat_chatro_room_ty_e6b83f_idx'),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(fields=['room', 'sent_at'], name='chat_chatme_room_id_05b860_idx'),
        ),
        migrations.AddIndex(
            model_name='chatroommember',
            index=models.Index(fields=['room', 'user'], name='chat_chatro_room_id_8597d4_idx'),
        ),
        migrations.AddIndex(
            model_name='chatreadreceipt',
            index=models.Index(fields=['room', 'user'], name='chat_chatre_room_id_2b2c6a_idx'),
        ),
    ]
