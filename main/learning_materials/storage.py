from cloudinary_storage.storage import RawMediaCloudinaryStorage


class LearningMaterialStorage(RawMediaCloudinaryStorage):
    """
    Store learning material PDFs as raw assets so Cloudinary delivers them directly.
    """
    pass
