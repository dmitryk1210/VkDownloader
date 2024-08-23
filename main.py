import os
import requests
import shutil
import yaml

from common.vk_api.vk_api import *
from common.vk_api.vk_api.audio import VkAudio

from datetime import datetime


config        = None
configPrivate = None


CONFIG_FILE_NAME = "config.yaml"
CONFIG_PRIVATE_FILE_NAME = "config.private.yaml"


def load_config():
    global config
    global configPrivate
    with open(CONFIG_FILE_NAME) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    if os.path.isfile(CONFIG_PRIVATE_FILE_NAME):
        with open(CONFIG_PRIVATE_FILE_NAME) as f:
            configPrivate = yaml.load(f, Loader=yaml.FullLoader)


def get_cvar(name):
    if config is None:
        load_config()
    if configPrivate is not None and configPrivate.get(name) is not None:
        return configPrivate.get(name)
    return config.get(name)
    

def is_image_extension(extension: str) -> bool:
    image_extensions = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp', 'ico'}
    return extension.lower() in image_extensions


def is_video_extension(extension: str) -> bool:
    video_extensions = {'mp4', 'mkv', 'mov', 'avi', 'flv', 'wmv', 'webm', 'mpeg', 'mpg', '3gp', 'm4v'}
    return extension.lower() in video_extensions


def query_yes_no(question):
    yes_list = ["yes", "y"]
    no_list  = ["no",  "n"]
    
    while True:
        inp = input(f"{question} [y/n]\n").lower()
        if inp in yes_list:
            return True
        elif inp in no_list:
            return False


def auth_handler():
    """ 
    This function is called if two-factor authentication is required
    """

    key = input("Enter authentication code: ")
    remember_device = True

    return key, remember_device


def process_photo(photo, chat_folder_full_path, urls_downloaded):
    strname = datetime.fromtimestamp(int(photo['date'])).strftime('IMG_%Y_%m_%d__%H_%M_%S')
    # print(strname)
    idx_best = 0
    size_best = -1
    for idx, photo_entity in enumerate(photo['sizes']):
        size_current_entity = photo_entity['height'] * photo_entity['width']
        if size_current_entity > size_best:
            size_best = size_current_entity
            idx_best = idx
    best_entity = photo['sizes'][idx_best]
    
    filepath = os.path.join(chat_folder_full_path, strname)
    if os.path.isfile(filepath + '.jpg'):
        if best_entity['url'] in urls_downloaded:
            return
        i = 1
        while(os.path.isfile(f"{filepath}_{str(i)}.jpg")):
            i += 1
        filepath = f"{filepath}_{str(i)}"

    raw_data = requests.get(best_entity['url']).content
    with open(filepath + '.jpg', 'wb') as handler:
        handler.write(raw_data)
    urls_downloaded.append(best_entity['url'])


"""
There you can add values that should be ignored:
1 - text documents
2 - archives
3 - gif
4 - image
5 - audio
6 - video
7 - e-books
8 - unknown
"""
DOC_IGNORE_BY_TYPE = [ 1, 2, 7 ]


"""
There you can add extensions (without commas) that should be saved.
Files with other extensions will be ignored.
For example:
'jpg',
'png',
'tga'

If there are no items in list, then all files will be saved
"""
DOC_FILTER_BY_TYPE = [ ]


PEER_ID_LIST = [ ]

def process_doc(doc, chat_folder_full_path, urls_downloaded):
    if doc['type'] in DOC_IGNORE_BY_TYPE:
        return
    if len(DOC_FILTER_BY_TYPE) > 0 and (doc['ext'] not in DOC_FILTER_BY_TYPE):
        return
    
    prefix = 'DOC'
    if is_image_extension(doc['ext']):
        prefix = 'IMG'
    elif is_video_extension(doc['ext']):
        prefix = 'VID'
    else:
        return
    
    strname = datetime.fromtimestamp(int(doc['date'])).strftime(f"{prefix}_%Y_%m_%d__%H_%M_%S_{doc['title']}")
    # print(strname)
    
    filepath = os.path.join(chat_folder_full_path, strname)
    if os.path.isfile(filepath):
        if doc['url'] in urls_downloaded:
            return
        i = 1
        while(os.path.isfile(f"{filepath}_{str(i)}.{doc['ext']}")):
            i += 1
        filepath = f"{filepath}_{str(i)}.{doc['ext']}"

    raw_data = requests.get(doc['url']).content
    with open(filepath, 'wb') as handler:
        handler.write(raw_data)
    urls_downloaded.append(doc['url'])


def process_message(msg, chat_folder_full_path, urls_downloaded):
    """
    documentation:
    https://dev.vk.com/ru/reference/objects/attachments-message
    """
    for attach in msg['attachments']:
        if attach['type'] == 'photo':
            process_photo(attach['photo'], chat_folder_full_path, urls_downloaded)
        if attach['type'] == 'doc':
            process_doc  (attach['doc'],   chat_folder_full_path, urls_downloaded)
        if attach['type'] == 'video':
            print(f"VIDEO IS NOT SUPPORTED, MSG INFO: id: {msg['id']}, date: {msg['date']}, peer_id: {msg['peer_id']}, from_id: {msg['from_id']}, text: {msg['text']}")

    if msg.get('fwd_messages') is None:
        return
    for fwd_msg in msg['fwd_messages']:
        process_message(fwd_msg, chat_folder_full_path, urls_downloaded)


def check_need_process_conversation(vk, conv_obj):
    peer_id     = conv_obj['conversation']['peer']['id']
    peer_type   = conv_obj['conversation']['peer']['type']
    chat_title  = ''
    chat_folder = ''
    if peer_type == 'user':
        # should use 'profiles' from getConversations methon instead
        users_data = vk.users.get(
            user_ids=peer_id
        )
        chat_title  = f"user {peer_id} ({users_data[0]['first_name']} {users_data[0]['last_name']})"
    elif peer_type == 'chat':
        chat_title  = f"chat {peer_id} ({conv_obj['conversation']['chat_settings']['title']})"
    elif peer_type == 'group':
        chat_title  = f"group {peer_id} (groups are not supported)"
        return False
    else:
        chat_title  = f"{peer_type} {peer_id} ({peer_type}s are not supported)"

    # get count of chat messages
    chat_attachments : dict = vk.messages.getHistory(
        offset=0,
        count=1,
        peer_id=peer_id
    )
    total_count_messages = chat_attachments['count']
    return query_yes_no(f"Do you want to process {chat_title} with {total_count_messages} messages?")


def process_conversation(vk, conv_obj):
    peer_id     = conv_obj['conversation']['peer']['id']
    peer_type   = conv_obj['conversation']['peer']['type']
    chat_title  = ''
    chat_folder = ''
    if peer_type == 'user':
        # should use 'profiles' from getConversations methon instead
        users_data = vk.users.get(
            user_ids=peer_id
        )
        chat_folder = f"{peer_id}_{users_data[0]['first_name']}_{users_data[0]['last_name']}"
    elif peer_type == 'chat':
        chat_folder = f"{peer_id}_{conv_obj['conversation']['chat_settings']['title']}"
    elif peer_type == 'group':
        chat_folder = f"{peer_id}_group"
    else:
        chat_folder = f"{peer_id}_{peer_type}"

    # get count of chat messages
    chat_attachments : dict = vk.messages.getHistory(
        offset=0,
        count=1,
        peer_id=peer_id
    )
    total_count_messages = chat_attachments['count']   
    chat_folder_full_path = os.path.join('output', chat_folder)

    print(f"current folder: {chat_folder}, messages to process: {total_count_messages}")
    
    if os.path.exists(chat_folder_full_path):
        shutil.rmtree(chat_folder_full_path)
    os.makedirs(chat_folder_full_path, exist_ok=True)

    urls_downloaded = []

    all_messages_loaded = False
    processed_count_messages = 0
    last_message_id = -1
    MESSAGES_COUNT_PER_REQUEST = 200 # max 200
    while(not all_messages_loaded):
        chat_attachments : dict = vk.messages.getHistory(
            offset=0,
            count=MESSAGES_COUNT_PER_REQUEST,
            peer_id=peer_id,
            start_message_id=last_message_id
        )
        chat_attachments_items = chat_attachments['items']

        total_count_messages = chat_attachments['count']
        for item in chat_attachments_items:
            if item['id'] == last_message_id:
                continue
            process_message(item, chat_folder_full_path, urls_downloaded)
            processed_count_messages += 1

        last_message_id = chat_attachments_items[-1]['id']
        all_messages_loaded = (len(chat_attachments_items) < MESSAGES_COUNT_PER_REQUEST)

        print(f"peer_id {peer_id}: messages processed: {processed_count_messages} of {total_count_messages}")


def main():
    login = get_cvar('login')
    if login is None:
        login = input("Enter login or phone number: ")

    password = get_cvar('password')
    if password is None:
        password = input("Enter password: ")

    vk_session = vk_api.VkApi(
        login=login, 
        password=password,
        app_id=get_cvar('app_id'),
        auth_handler=auth_handler
    )

    try:
        vk_session.auth()
    except vk_api.AuthError as error_msg:
        print(error_msg)
        return
    
    print('user_id: ', vk_session.token['user_id'])
    print('access_token: ', vk_session.token['access_token'])

    vk = vk_session.get_api()

    # get count of chat messages
    conversations : dict = vk.messages.getConversations(
        offset=0,
        count=1
    )
    total_count_conversations = conversations['count']
    CONVERSATIONS_COUNT_PER_REQUEST = 100 # max 200

    offset = 0
    prepared_count_conversations = 0
    conversations_to_process = []
    while offset < total_count_conversations:
        conversations : dict = vk.messages.getConversations(
            offset=offset,
            count=CONVERSATIONS_COUNT_PER_REQUEST
        )
        offset += CONVERSATIONS_COUNT_PER_REQUEST

        if conversations.get('items') is None:
            return
        
        for conv_obj in conversations.get('items'):
            prepared_count_conversations += 1
            if len(PEER_ID_LIST) == 0:
                if not check_need_process_conversation(vk, conv_obj):
                    continue
            else:
                if conv_obj['conversation']['peer']['id'] not in PEER_ID_LIST:
                    continue
            conversations_to_process.append(conv_obj)
    
    print(f"conversations prepared: {prepared_count_conversations} of {total_count_conversations}")
    print(f"conversations to process: {len(conversations_to_process)}")

    print(f"peer ids: {len(conversations_to_process)}")
    for conv_obj in conversations_to_process:
        print(conv_obj['conversation']['peer']['id'])
        

    for idx, conv_obj in enumerate(conversations_to_process):
        print(f"processing conversation {idx + 1} of {len(conversations_to_process)}")
        process_conversation(vk, conv_obj)
    

if __name__ == '__main__':
    main()
