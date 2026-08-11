import os
import re
import urllib.request
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from boutique.models import UserProfile


STAFF_URL = 'https://www.unak.is/is/starfsfolk'


class Command(BaseCommand):
    help = 'Fetch staff photos from unak.is and assign them as user avatars'

    def add_arguments(self, parser):
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing avatars',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Only fetch for a specific user email',
        )

    def handle(self, *args, **options):
        self.stdout.write('Fetching staff directory from unak.is...')
        try:
            req = urllib.request.Request(STAFF_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode('utf-8')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to fetch staff page: {e}'))
            return

        # Build email -> image URL mapping from the HTML
        # Pattern: img src followed by mailto link in the same staff entry
        email_to_img = {}
        # Find all image URLs
        img_pattern = re.compile(
            r'<img[^>]+src="(https://ugla\.unak\.is/pub/unak/haskolaborgarar/mynd/[^"]+)"'
        )
        # Find all mailto links
        mailto_pattern = re.compile(r'<a[^>]+href="mailto:([^"]+)"')

        # Split HTML into chunks by staff entry
        # Each entry typically has an img (optional) followed by name, title, and mailto
        # We'll scan line by line and associate images with the next mailto we find
        current_img = None
        for line in html.split('\n'):
            img_match = img_pattern.search(line)
            if img_match:
                current_img = img_match.group(1)

            mailto_match = mailto_pattern.search(line)
            if mailto_match:
                email = mailto_match.group(1).lower()
                if current_img:
                    email_to_img[email] = current_img
                current_img = None

        self.stdout.write(f'Found {len(email_to_img)} staff members with photos')

        # Match against our users
        if options['user']:
            users = User.objects.filter(email__iexact=options['user'])
        else:
            users = User.objects.filter(groups__name='person', is_active=True)

        matched = 0
        skipped = 0
        not_found = 0

        for user in users:
            profile, _ = UserProfile.objects.get_or_create(user=user)

            if profile.profile_img and not options['overwrite']:
                skipped += 1
                self.stdout.write(f'  SKIP {user.email} (already has avatar)')
                continue

            email = user.email.lower()
            img_url = email_to_img.get(email)

            if not img_url:
                not_found += 1
                self.stdout.write(self.style.WARNING(
                    f'  MISS {user.get_full_name()} ({email}) - not found on unak.is'
                ))
                continue

            try:
                req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as img_response:
                    img_data = img_response.read()

                ext = os.path.splitext(img_url)[1] or '.jpg'
                filename = f'{email.split("@")[0]}{ext}'
                profile.profile_img.save(filename, ContentFile(img_data), save=True)
                matched += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  OK   {user.get_full_name()} ({email})'
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f'  FAIL {user.get_full_name()} ({email}): {e}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {matched} fetched, {skipped} skipped, {not_found} not found'
        ))
