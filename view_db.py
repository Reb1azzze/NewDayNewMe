from database import get_all_users

for user in get_all_users():
    print(f"Chat ID: {user['chat_id']}, City: {user['city']}, Time: {user['send_time']}")