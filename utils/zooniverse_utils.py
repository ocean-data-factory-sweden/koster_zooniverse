from panoptes_client import (
    SubjectSet,
    Subject,
    Project,
    Panoptes,
)  # needed to upload clips to Zooniverse


class AuthenticationError(Exception):
    pass


def auth_session(username, password):
    # Connect to Zooniverse with your username and password
    auth = Panoptes.connect(username=username, password=password)

    if not auth.logged_in:
        raise AuthenticationError("Your credentials are invalid. Please try again.")

    # Specify the project number of the koster lab
    project = Project(9747)

    return project
