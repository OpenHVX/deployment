#!/usr/bin/env python3
"""Build/import one release, then publish its local receipt for promotion.

Nothing updates the tracked Kubernetes release automatically. If a build/import
fails, leave its artifacts for diagnosis and rerun to create a new candidate.
"""
from image_sources import prepare_release

from lab_runtime import WORK, ensure_lab_lock, run_playbook


def main():
    ensure_lab_lock()
    tag, release = prepare_release()
    run_playbook('images', variables={'image_tag': tag, 'image_release_dir': str(release)})
    # Publish the candidate only after every node accepted the same image bundle.
    # Older successful receipts remain in releases/<tag>/ for rollback/auditing.
    temporary = WORK / 'image-tag.new'
    temporary.write_text(tag + '\n')
    temporary.replace(WORK / 'image-tag')
    print(f'Release imported: {tag}\nReceipt: {release / "image-receipt.json"}')
    print('Review/promote the tag in kubernetes/overlays/lab/kustomization.yaml.')


if __name__ == '__main__':
    main()
