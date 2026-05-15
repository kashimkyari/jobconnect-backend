import aiosmtplib
import asyncio
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict, Any
import logging
from pathlib import Path
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ..config import settings

logger = logging.getLogger(__name__)

class EmailTemplateRenderer:
    """Jinja2 template renderer for emails"""
    
    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'emails')
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
    
    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render a template with the given context"""
        # Add default context variables
        default_context = {
            'app_url': settings.API_BASE_URL,
            'mail_from': settings.MAIL_FROM,
        }
        default_context.update(context)
        
        template = self.env.get_template(template_name)
        return template.render(**default_context)


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    retries: int = 3,
    initial_delay: int = 5
) -> bool:
    """
    Send email using SMTP relay with retry mechanism
    """
    message = MIMEMultipart("alternative")
    message["From"] = f"{settings.MAIL_SENDER_NAME} <{settings.MAIL_FROM}>"
    message["To"] = to_email
    message["Subject"] = subject

    if cc:
        message["Cc"] = ", ".join(cc)
    if bcc:
        message["Bcc"] = ", ".join(bcc)

    message.attach(MIMEText(body, "plain"))
    if html:
        message.attach(MIMEText(html, "html"))

    for attempt in range(retries):
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.MAIL_SERVER,
                port=settings.MAIL_PORT,
                username=settings.MAIL_USERNAME,
                password=settings.MAIL_PASSWORD,
                use_tls=settings.MAIL_USE_SSL,
                start_tls=settings.MAIL_STARTTLS
            )
            logger.info(f"Email sent successfully to {to_email} on attempt {attempt + 1}", extra={
                "subject": subject,
                "recipient": to_email,
                "attempt": attempt + 1
            })
            return True
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for sending email to {to_email}: {str(e)}", extra={
                "subject": subject,
                "recipient": to_email,
                "attempt": attempt + 1,
                "error": str(e)
            })
            if attempt < retries - 1:
                delay = initial_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

    logger.error(f"Failed to send email to {to_email} after {retries} attempts.", extra={
        "subject": subject,
        "recipient": to_email,
    })
    return False


class EmailService:
    """Email service with template rendering"""
    
    def __init__(self):
        self.renderer = EmailTemplateRenderer()
    
    async def send_template_email(
        self,
        to_email: str,
        template_name: str,
        subject: str,
        context: Dict[str, Any],
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Send an email using a Jinja2 template
        """
        try:
            html_content = self.renderer.render(template_name, context)
            return await send_email(
                to_email=to_email,
                subject=subject,
                body=subject,  # Plain text fallback
                html=html_content,
                cc=cc,
                bcc=bcc
            )
        except Exception as e:
            logger.error(f"Error rendering email template {template_name}: {str(e)}")
            return False
    
    async def send_welcome_email(
        self,
        to_email: str,
        first_name: str,
        user_type: str,
        action_url: str
    ) -> bool:
        """Send welcome email to new user"""
        context = {
            'first_name': first_name,
            'user_type': user_type,
            'action_url': action_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='welcome.html',
            subject='Welcome to JobConnect!',
            context=context
        )
    
    async def send_email_verification(
        self,
        to_email: str,
        first_name: str,
        otp: str,
        verification_url: str
    ) -> bool:
        """Send email verification code"""
        context = {
            'first_name': first_name,
            'otp': otp,
            'verification_url': verification_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='email_verification.html',
            subject='Verify Your Email Address',
            context=context
        )
    
    async def send_password_reset(
        self,
        to_email: str,
        first_name: str,
        otp: str,
        reset_url: str
    ) -> bool:
        """Send password reset email"""
        context = {
            'first_name': first_name,
            'otp': otp,
            'reset_url': reset_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='password_reset.html',
            subject='Reset Your Password',
            context=context
        )
    
    async def send_account_locked_email(
        self,
        to_email: str,
        first_name: str,
        locked_at: str,
        unlock_time: str,
        time_remaining: str
    ) -> bool:
        """Send account locked notification"""
        context = {
            'first_name': first_name,
            'locked_at': locked_at,
            'unlock_time': unlock_time,
            'time_remaining': time_remaining,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='account_locked.html',
            subject='Your Account Has Been Temporarily Locked',
            context=context
        )
    
    async def send_new_application_notification(
        self,
        to_email: str,
        employer_name: str,
        job_title: str,
        candidate_name: str,
        applied_date: str,
        candidate_summary: str,
        candidate_email: str,
        application_url: str,
        candidate_url: str,
        candidate_rating: Optional[float] = None
    ) -> bool:
        """Send new job application notification to employer"""
        context = {
            'employer_name': employer_name,
            'job_title': job_title,
            'candidate_name': candidate_name,
            'applied_date': applied_date,
            'candidate_summary': candidate_summary,
            'candidate_email': candidate_email,
            'application_url': application_url,
            'candidate_url': candidate_url,
            'candidate_rating': candidate_rating,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='new_application.html',
            subject=f'New application for {job_title}',
            context=context
        )
    
    async def send_application_status_update(
        self,
        to_email: str,
        candidate_name: str,
        job_title: str,
        company_name: str,
        status: str,
        status_label: str,
        updated_date: str,
        application_url: str,
        job_search_url: str,
        interview_date: Optional[str] = None,
        interview_time: Optional[str] = None,
        interview_format: Optional[str] = None,
        feedback: Optional[str] = None
    ) -> bool:
        """Send application status update to candidate"""
        context = {
            'candidate_name': candidate_name,
            'job_title': job_title,
            'company_name': company_name,
            'status': status,
            'status_label': status_label,
            'updated_date': updated_date,
            'application_url': application_url,
            'job_search_url': job_search_url,
            'interview_date': interview_date,
            'interview_time': interview_time,
            'interview_format': interview_format,
            'feedback': feedback,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='application_status.html',
            subject=f'Update on your application for {job_title}',
            context=context
        )
    
    async def send_new_message_notification(
        self,
        to_email: str,
        recipient_name: str,
        sender_name: str,
        message_date: str,
        message_preview: str,
        message_url: str,
        conversation_url: str,
        context_title: Optional[str] = None,
        context_type: Optional[str] = None,
        message_truncated: bool = False
    ) -> bool:
        """Send new message notification"""
        context = {
            'recipient_name': recipient_name,
            'sender_name': sender_name,
            'message_date': message_date,
            'message_preview': message_preview,
            'message_url': message_url,
            'conversation_url': conversation_url,
            'context_title': context_title,
            'context_type': context_type,
            'message_truncated': message_truncated,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='new_message.html',
            subject=f'New message from {sender_name}',
            context=context
        )
    
    async def send_kyc_verification_update(
        self,
        to_email: str,
        first_name: str,
        status: str,
        status_label: str,
        submission_date: str,
        reviewed_date: Optional[str] = None,
        estimated_date: Optional[str] = None,
        feedback: Optional[str] = None,
        dashboard_url: Optional[str] = None,
        resubmit_url: Optional[str] = None
    ) -> bool:
        """Send KYC verification status update"""
        context = {
            'first_name': first_name,
            'status': status,
            'status_label': status_label,
            'submission_date': submission_date,
            'reviewed_date': reviewed_date,
            'estimated_date': estimated_date,
            'feedback': feedback,
            'dashboard_url': dashboard_url,
            'resubmit_url': resubmit_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='kyc_verification.html',
            subject='KYC Verification Update',
            context=context
        )
    
    async def send_new_review_notification(
        self,
        to_email: str,
        recipient_name: str,
        reviewer_name: str,
        rating: int,
        review_date: str,
        review_url: str,
        profile_url: str,
        job_title: Optional[str] = None,
        review_text: Optional[str] = None
    ) -> bool:
        """Send new review notification"""
        context = {
            'recipient_name': recipient_name,
            'reviewer_name': reviewer_name,
            'rating': rating,
            'review_date': review_date,
            'review_url': review_url,
            'profile_url': profile_url,
            'job_title': job_title,
            'review_text': review_text,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='new_review.html',
            subject='You\'ve Received a New Review',
            context=context
        )
    
    async def send_moderation_notice(
        self,
        to_email: str,
        first_name: str,
        content_type: str,
        action: str,
        action_label: str,
        action_date: str,
        guidelines_url: str,
        reason: Optional[str] = None,
        appeal_url: Optional[str] = None
    ) -> bool:
        """Send content moderation notice"""
        context = {
            'first_name': first_name,
            'content_type': content_type,
            'action': action,
            'action_label': action_label,
            'action_date': action_date,
            'guidelines_url': guidelines_url,
            'reason': reason,
            'appeal_url': appeal_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='moderation_notice.html',
            subject='Content Moderation Notice',
            context=context
        )
    
    async def send_dispute_resolution_update(
        self,
        to_email: str,
        user_name: str,
        dispute_id: str,
        job_title: str,
        other_party_name: str,
        resolution_date: str,
        resolution_summary: str,
        resolution_type: str,
        dispute_url: str,
        financial_details: Optional[List[Dict[str, str]]] = None,
        appeal_deadline: Optional[str] = None,
        appeal_url: Optional[str] = None
    ) -> bool:
        """Send dispute resolution update"""
        context = {
            'user_name': user_name,
            'dispute_id': dispute_id,
            'job_title': job_title,
            'other_party_name': other_party_name,
            'resolution_date': resolution_date,
            'resolution_summary': resolution_summary,
            'resolution_type': resolution_type,
            'dispute_url': dispute_url,
            'financial_details': financial_details,
            'appeal_deadline': appeal_deadline,
            'appeal_url': appeal_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='dispute_resolution.html',
            subject='Dispute Resolution Update',
            context=context
        )
    
    async def send_payment_received_notification(
        self,
        to_email: str,
        recipient_name: str,
        amount: str,
        transaction_id: str,
        transaction_date: str,
        payer_name: str,
        wallet_url: str,
        transaction_url: str,
        payment_method: Optional[str] = None,
        reference: Optional[str] = None
    ) -> bool:
        """Send payment received notification"""
        context = {
            'recipient_name': recipient_name,
            'amount': amount,
            'transaction_id': transaction_id,
            'transaction_date': transaction_date,
            'payer_name': payer_name,
            'wallet_url': wallet_url,
            'transaction_url': transaction_url,
            'payment_method': payment_method,
            'reference': reference,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='payment_received.html',
            subject=f'Payment Received - {amount}',
            context=context
        )
    
    async def send_job_posted_confirmation(
        self,
        to_email: str,
        employer_name: str,
        job_title: str,
        location: str,
        job_id: str,
        posted_date: str,
        job_url: str,
        manage_url: str,
        job_link: str,
        expiry_date: Optional[str] = None
    ) -> bool:
        """Send job posted confirmation"""
        context = {
            'employer_name': employer_name,
            'job_title': job_title,
            'location': location,
            'job_id': job_id,
            'posted_date': posted_date,
            'job_url': job_url,
            'manage_url': manage_url,
            'job_link': job_link,
            'expiry_date': expiry_date,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='job_posted.html',
            subject='Your Job Has Been Posted!',
            context=context
        )
    
    async def send_subscription_confirmation(
        self,
        to_email: str,
        user_name: str,
        plan_name: str,
        billing_cycle: str,
        amount: str,
        start_date: str,
        renewal_date: str,
        dashboard_url: str,
        settings_url: str,
        help_url: str,
        tutorials_url: str,
        support_url: str,
        next_billing_date: Optional[str] = None,
        features: Optional[List[str]] = None
    ) -> bool:
        """Send subscription confirmation email"""
        context = {
            'user_name': user_name,
            'plan_name': plan_name,
            'billing_cycle': billing_cycle,
            'amount': amount,
            'start_date': start_date,
            'renewal_date': renewal_date,
            'dashboard_url': dashboard_url,
            'settings_url': settings_url,
            'help_url': help_url,
            'tutorials_url': tutorials_url,
            'support_url': support_url,
            'next_billing_date': next_billing_date,
            'features': features,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='subscription_confirmation.html',
            subject=f'Welcome to {plan_name}!',
            context=context
        )
    
    async def send_monthly_digest(
        self,
        to_email: str,
        user_name: str,
        user_type: str,
        month: str,
        dashboard_url: str,
        action_url: str,
        active_jobs: Optional[int] = None,
        new_applications: Optional[int] = None,
        candidates_interviewed: Optional[int] = None,
        positions_filled: Optional[int] = None,
        applications_sent: Optional[int] = None,
        interviews_scheduled: Optional[int] = None,
        profile_views: Optional[int] = None,
        skills_endorsed: Optional[int] = None,
        top_candidate: Optional[Dict[str, Any]] = None,
        top_job: Optional[Dict[str, Any]] = None,
        recent_activity: Optional[List[str]] = None
    ) -> bool:
        """Send monthly digest email"""
        context = {
            'user_name': user_name,
            'user_type': user_type,
            'month': month,
            'dashboard_url': dashboard_url,
            'action_url': action_url,
            'active_jobs': active_jobs,
            'new_applications': new_applications,
            'candidates_interviewed': candidates_interviewed,
            'positions_filled': positions_filled,
            'applications_sent': applications_sent,
            'interviews_scheduled': interviews_scheduled,
            'profile_views': profile_views,
            'skills_endorsed': skills_endorsed,
            'top_candidate': top_candidate,
            'top_job': top_job,
            'recent_activity': recent_activity,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='monthly_digest.html',
            subject=f'Your JobConnect Monthly Digest - {month}',
            context=context
        )
    
    async def send_activity_alert(
        self,
        to_email: str,
        first_name: str,
        activity_type: str,
        location: str,
        device: str,
        ip_address: str,
        activity_time: str,
        activity_description: str,
        confirm_url: str,
        deny_url: str,
        security_url: str
    ) -> bool:
        """Send account activity alert"""
        context = {
            'first_name': first_name,
            'activity_type': activity_type,
            'location': location,
            'device': device,
            'ip_address': ip_address,
            'activity_time': activity_time,
            'activity_description': activity_description,
            'confirm_url': confirm_url,
            'deny_url': deny_url,
            'security_url': security_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='activity_alert.html',
            subject='Account Security Alert',
            context=context
        )
    
    async def send_referral_reward(
        self,
        to_email: str,
        first_name: str,
        reward_amount: str,
        referred_user_name: str,
        reward_type: str,
        reward_date: str,
        total_referrals: int,
        total_earnings: str,
        referral_link: str,
        referral_dashboard_url: str,
        wallet_url: str
    ) -> bool:
        """Send referral reward notification"""
        context = {
            'first_name': first_name,
            'reward_amount': reward_amount,
            'referred_user_name': referred_user_name,
            'reward_type': reward_type,
            'reward_date': reward_date,
            'total_referrals': total_referrals,
            'total_earnings': total_earnings,
            'referral_link': referral_link,
            'referral_dashboard_url': referral_dashboard_url,
            'wallet_url': wallet_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='referral_reward.html',
            subject='You\'ve Earned a Referral Reward!',
            context=context
        )
    
    async def send_action_required(
        self,
        to_email: str,
        first_name: str,
        action_title: str,
        action_description: str,
        action_url: str,
        support_url: str,
        steps: List[str],
        deadline: Optional[str] = None,
        time_remaining: Optional[str] = None,
        reason: Optional[str] = None,
        consequences: Optional[str] = None,
        help_url: Optional[str] = None
    ) -> bool:
        """Send action required notification"""
        context = {
            'first_name': first_name,
            'action_title': action_title,
            'action_description': action_description,
            'action_url': action_url,
            'support_url': support_url,
            'steps': steps,
            'deadline': deadline,
            'time_remaining': time_remaining,
            'reason': reason,
            'consequences': consequences,
            'help_url': help_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='action_required.html',
            subject='Action Required on Your Account',
            context=context
        )

    async def send_withdrawal_request_submitted(
        self,
        to_email: str,
        user_name: str,
        withdrawal_amount: str,
        tax_amount: str,
        total_amount: str,
        tax_rate: str,
        bank_name: str,
        account_number_last_4: str,
        request_date: str,
        dashboard_url: str
    ) -> bool:
        """Send withdrawal request submitted notification"""
        context = {
            'user_name': user_name,
            'withdrawal_amount': withdrawal_amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'tax_rate': tax_rate,
            'bank_name': bank_name,
            'account_number_last_4': account_number_last_4,
            'request_date': request_date,
            'dashboard_url': dashboard_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='withdrawal_request_submitted.html',
            subject='Withdrawal Request Submitted - Pending Review',
            context=context
        )

    async def send_withdrawal_approved(
        self,
        to_email: str,
        user_name: str,
        withdrawal_amount: str,
        tax_amount: str,
        total_amount: str,
        bank_name: str,
        account_number_last_4: str,
        approved_date: str,
        dashboard_url: str,
        transfer_reference: Optional[str] = None,
        admin_notes: Optional[str] = None
    ) -> bool:
        """Send withdrawal approved notification"""
        context = {
            'user_name': user_name,
            'withdrawal_amount': withdrawal_amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'bank_name': bank_name,
            'account_number_last_4': account_number_last_4,
            'approved_date': approved_date,
            'dashboard_url': dashboard_url,
            'transfer_reference': transfer_reference,
            'admin_notes': admin_notes,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='withdrawal_approved.html',
            subject='Your Withdrawal Has Been Approved',
            context=context
        )

    async def send_withdrawal_declined(
        self,
        to_email: str,
        user_name: str,
        withdrawal_amount: str,
        total_amount: str,
        bank_name: str,
        account_number_last_4: str,
        declined_date: str,
        dashboard_url: str,
        decline_reason: Optional[str] = None,
        support_url: Optional[str] = None,
        faq_url: Optional[str] = None
    ) -> bool:
        """Send withdrawal declined notification"""
        context = {
            'user_name': user_name,
            'withdrawal_amount': withdrawal_amount,
            'total_amount': total_amount,
            'bank_name': bank_name,
            'account_number_last_4': account_number_last_4,
            'declined_date': declined_date,
            'dashboard_url': dashboard_url,
            'decline_reason': decline_reason,
            'support_url': support_url,
            'faq_url': faq_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='withdrawal_declined.html',
            subject='Your Withdrawal Request Was Declined',
            context=context
        )

    async def send_withdrawal_completed(
        self,
        to_email: str,
        user_name: str,
        withdrawal_amount: str,
        total_amount: str,
        bank_name: str,
        account_number_last_4: str,
        transfer_date: str,
        dashboard_url: str,
        transfer_reference: Optional[str] = None,
        support_url: Optional[str] = None
    ) -> bool:
        """Send withdrawal completed notification"""
        context = {
            'user_name': user_name,
            'withdrawal_amount': withdrawal_amount,
            'total_amount': total_amount,
            'bank_name': bank_name,
            'account_number_last_4': account_number_last_4,
            'transfer_date': transfer_date,
            'dashboard_url': dashboard_url,
            'transfer_reference': transfer_reference,
            'support_url': support_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='withdrawal_completed.html',
            subject='Your Withdrawal Has Been Transferred',
            context=context
        )

    async def send_withdrawal_failed(
        self,
        to_email: str,
        user_name: str,
        withdrawal_amount: str,
        total_amount: str,
        bank_name: str,
        account_number_last_4: str,
        failed_date: str,
        dashboard_url: str,
        transfer_reference: Optional[str] = None,
        support_url: Optional[str] = None
    ) -> bool:
        """Send withdrawal failed notification"""
        context = {
            'user_name': user_name,
            'withdrawal_amount': withdrawal_amount,
            'total_amount': total_amount,
            'bank_name': bank_name,
            'account_number_last_4': account_number_last_4,
            'failed_date': failed_date,
            'dashboard_url': dashboard_url,
            'transfer_reference': transfer_reference,
            'support_url': support_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='withdrawal_failed.html',
            subject='Withdrawal Transfer Failed - Funds Restored',
            context=context
        )

    async def send_withdrawal_dispute_created(
        self,
        to_email: str,
        user_name: str,
        dispute_id: int,
        withdrawal_amount: str,
        total_amount: str,
        bank_name: str,
        account_number_last_4: str,
        failure_reason: str,
        created_date: str,
        dashboard_url: str,
        support_url: Optional[str] = None
    ) -> bool:
        """Send withdrawal dispute created notification"""
        context = {
            'user_name': user_name,
            'dispute_id': dispute_id,
            'withdrawal_amount': withdrawal_amount,
            'total_amount': total_amount,
            'bank_name': bank_name,
            'account_number_last_4': account_number_last_4,
            'failure_reason': failure_reason,
            'created_date': created_date,
            'dashboard_url': dashboard_url,
            'support_url': support_url,
        }
        return await self.send_template_email(
            to_email=to_email,
            template_name='withdrawal_dispute_created.html',
            subject='Withdrawal Transfer Issue - Support Case Opened',
            context=context
        )

