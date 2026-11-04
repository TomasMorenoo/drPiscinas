import json
import os

def enviar_push_novedades(titulo, cuerpo):
    try:
        from pywebpush import webpush, WebPushException
        from app.models.push_subscription import PushSubscription
        from app.models.user import User
        from app import db

        vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY', '')
        vapid_email = os.environ.get('VAPID_EMAIL', 'admin@example.com')

        if not vapid_private_key:
            return

        admin_ids = [u.id for u in User.query.filter(
            db.or_(User.rol.in_(['admin', 'demo']), User.username == 'root')
        ).all()]

        subs = PushSubscription.query.filter(PushSubscription.user_id.in_(admin_ids)).all()
        payload = json.dumps({'title': titulo, 'body': cuerpo})
        stale = []

        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={'sub': f'mailto:{vapid_email}'}
                )
            except WebPushException as e:
                if e.response and e.response.status_code in (404, 410):
                    stale.append(sub.id)
            except Exception:
                pass

        if stale:
            PushSubscription.query.filter(PushSubscription.id.in_(stale)).delete()
            db.session.commit()

    except Exception:
        pass
