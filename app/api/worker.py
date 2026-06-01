import os
from dotenv import load_dotenv
from celery import Celery
from app.services.whatsapp import send_text, send_template
from app.services.memory import is_pending_followup, remove_pending_followup
from app.core.config import settings
load_dotenv()

celery_app = Celery("followup_tasks", broker=settings.REDIS_URL, backend=settings.REDIS_URL)


@celery_app.task
def send_welcome_followup(wa_id, retry_num=0, reservation_id="default"):
    from app.services.memory import is_pending_followup, remove_pending_followup, update_pending_task_type
    import logging
    
    # We use a dedicated logger for the worker
    worker_logger = logging.getLogger("celery_worker")
    
    if is_pending_followup(wa_id, reservation_id):
        # Determine which template to send based on the retry number
        if retry_num == 0:
            template_name = "get_special_request"
            countdown = settings.FOLLOWUP_COUNTDOWN_SECONDS
            update_pending_task_type(wa_id, "get_special_request", reservation_id)
            flow_token = "1675348800480607"
            components = [
                {
                    "type": "button",
                    "sub_type": "flow",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "action",
                            "action": {
                                "flow_token": flow_token
                            }
                        }
                    ]
                }
            ]
        else:
            template_name = "reminder_special_requests"
            countdown = None 
            update_pending_task_type(wa_id, "reminder_special_request", reservation_id)
            components = [] 
        
        # Send the template
        worker_logger.info(f"Sending follow-up template '{template_name}' to {wa_id} (retry={retry_num})")
        resp = send_template(wa_id, template_name=template_name, language_code="en", components=components)
        
        if resp:
            worker_logger.info(f"Template {template_name} sent successfully to {wa_id}. Resp: {resp}")
        else:
            worker_logger.error(f"Failed to send template {template_name} to {wa_id}. This usually means a template parameter mismatch.")
        
        # If there is a next step in the flow, schedule it (ONLY if the current one succeeded)
        if countdown and resp:
            send_welcome_followup.apply_async(
                args=[wa_id, retry_num + 1, reservation_id], 
                countdown=countdown
            )
            worker_logger.info(f"Scheduled next follow-up for {wa_id} in {countdown} seconds.")
        else:
            # If no more steps, or failure, we clear the task from memory
            remove_pending_followup(wa_id, reservation_id)
            worker_logger.info(f"Follow-up flow ended for {wa_id}.")
    else:
        worker_logger.info(f"Follow-up canceled for {wa_id} (no pending record).")
        pass

@celery_app.task
def send_test_followup(wa_id):
    """
    Test task: Checks if the user replied within the 1-minute window.
    If they haven't (is_pending_followup == True), it sends a reminder message.
    """
    if is_pending_followup(wa_id):
        msg = "Hey! It's been 1 minute since our last message. Are you still there?"
        send_text(wa_id=wa_id, text=msg)
        remove_pending_followup(wa_id)
    else:
        print(f"User {wa_id} already replied. Test follow-up canceled.")
        pass
