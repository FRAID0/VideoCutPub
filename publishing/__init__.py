"""
VideoCutPub - Publishing and Social Packaging Module (Étape 10)
Exposes SocialPackager, PublishingJob, AccountManager, and multi-platform publishers.
"""

from publishing.social_packager import (
    SegmentPack,
    PackSummary,
    SocialPackager,
)
from publishing.publishing_models import (
    PublishPlatform,
    PublishStatus,
    PrivacyLevel,
    AccountMetadata,
    AccountCredentials,
    PublishingJob,
)
from publishing.account_manager import AccountManager
from publishing.publisher_base import BasePublisher
from publishing.manual_publisher import ManualPublisher, META_WEB_PORTAL
from publishing.youtube_publisher import YouTubePublisher
from publishing.tiktok_publisher import TikTokPublisher
from publishing.publish_queue import PublishQueueManager

__all__ = [
    "SegmentPack",
    "PackSummary",
    "SocialPackager",
    "PublishPlatform",
    "PublishStatus",
    "PrivacyLevel",
    "AccountMetadata",
    "AccountCredentials",
    "PublishingJob",
    "AccountManager",
    "BasePublisher",
    "ManualPublisher",
    "META_WEB_PORTAL",
    "YouTubePublisher",
    "TikTokPublisher",
    "PublishQueueManager",
]
