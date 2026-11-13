"""shshd-runtime: Data Management's Add-Ons page (owner, 2026-11-02; docs/ADDONS.md): a row per addon of a library, each opening its
details, Export and Delete. The game's menu and the chooser's differ only in how they ask and open the library, which `host` gives:
    host.rows(screen, title, rows, parent), host.text(screen, title, body, parent), host.notice(title, text),
    host.confirm(title, text, verb, action), host.job(title, work, done), where work(library) runs off the UI thread, and
    host.deleted(), after a delete, for what the app keeps of the library.
"""

ROOT = 'options:data'
PAGE, DETAILS_PAGE, INFO_PAGE = 'data:addons', 'data:addon', 'data:addon_info'
ROW, DETAILS, EXPORT, DELETE = 'addon:', 'addon_details:', 'addon_export:', 'addon_delete:'
LISTED_USERS = 12                       # episodes named on the details page; more are counted


def needs(count):
    return f'{count} episode{" needs" if count == 1 else "s need"} it'


class AddonPages:
    def __init__(self, app, host):
        self.app, self.host = app, host
        self.summaries = {}             # the open list's addons by id, read off the UI thread

    def open(self):
        """The list, read under the busy card: which episodes need an addon means reading their records."""
        self.host.job('Reading add-ons', self._read, self._listed)

    def _read(self, library):
        summaries = {}
        # The first read of a library opens every episode's file (ContentLibrary.episode_requires keeps what it finds).
        for index, record in enumerate(library.episodes):
            self.app.progress_text = f'Episode {index + 1} of {len(library.episodes)}'
            library.episode_requires(record)
        for record in library.addons:
            users = library.addon_users(record)
            path = library.directory / record['file']
            summaries[record['id']] = dict(title=record['title'], addon=record['addon'], revision=record['revision'],
                                           size=path.stat().st_size if path.is_file() else None,
                                           users=[user['titles'][0] for user in users],
                                           supersedes=sorted(record.get('supersedes', ())))
        return summaries

    def _listed(self, summaries):
        self.summaries = summaries
        if not summaries:
            self.host.notice('No Add-Ons', 'This library has no add-ons. Add Episodes imports one from its file.')
            return
        self.host.rows(PAGE, 'Add-Ons', [(ROW + key, summary['title']) for key, summary in summaries.items()], ROOT)

    def command(self, key):
        """A row of these pages; whether it was one."""
        if key.startswith(ROW):
            addon = key[len(ROW):]
            # (A pack's name can be too long for a page's title, so it's in the row.)
            self.host.rows(DETAILS_PAGE, 'Add-On', [(DETAILS + addon, f'Details: {self.summaries[addon]["title"]}'),
                                                    (EXPORT + addon, 'Export'), (DELETE + addon, 'Delete')], PAGE)
        elif key.startswith(DETAILS):
            self.show_details(key[len(DETAILS):])
        elif key.startswith(EXPORT):
            self.export(key[len(EXPORT):])
        elif key.startswith(DELETE):
            self.delete(key[len(DELETE):])
        else:
            return False
        return True

    def show_details(self, addon):
        from .application import size_text
        summary = self.summaries[addon]
        users = summary['users']
        lines = [summary['title'], '', f'Add-on ID: {summary["addon"]}', f'Revision: {summary["revision"]}',
                 f'Size: {size_text(summary["size"]) if summary["size"] is not None else "its file is missing"}']
        if summary['supersedes']:
            lines.append(f'Replaces: {", ".join(summary["supersedes"])}')
        lines += ['', f'{len(users)} episode{"s" if len(users) != 1 else ""} need{"s" if len(users) == 1 else ""} it.']
        lines += [f'- {title}' for title in users[:LISTED_USERS]]
        if len(users) > LISTED_USERS:
            lines.append(f'and {len(users) - LISTED_USERS} more.')
        if not users:
            lines.append('Something may still use it by itself, as the X360 Arena Skin and Claire Hart portraits do.')
        self.host.text(INFO_PAGE, 'Add-On Details', '\n'.join(lines), DETAILS_PAGE)

    def export(self, addon):
        self.host.job('Exporting add-on', lambda library: self.app.export_addons(library, [addon]),
                      lambda result: self.host.notice(*result))

    def delete(self, addon):
        summary = self.summaries[addon]
        users = len(summary['users'])
        warning = (f'{needs(users).capitalize()}, and {"it" if users == 1 else "they"} won\'t start until the add-on is '
                   'imported again. Saved games stay.' if users else 'No episode needs it. Add Episodes brings it back from its file.')

        def run():
            self.host.job('Deleting add-on', lambda library: library.remove_addons([addon]), self._deleted)
        self.host.confirm('Delete Add-On?', f'{summary["title"]} will be deleted. {warning}', 'Delete', run)

    def _deleted(self, count):
        self.host.deleted()
        self.open()


def export_offer(app, host, result, library_job):
    """After Export Episodes: what it did, and when the episodes need addons, the offer to export those as well (owner, 2026-11-02:
    an episode doesn't work without them, but they're the player's to choose). `result`: (its notice, the addons' [(id, title)]);
    `library_job(title, work, done)` runs off the UI thread with the library."""
    (title, message), addons = result
    if not addons:
        host.notice(title, message)
        return
    names = ' and '.join(name for _, name in addons)
    plural = len(addons) != 1

    def run():
        library_job(f'Exporting add-on{"s" if plural else ""}', lambda library: app.export_addons(library, [key for key, _ in addons]),
                    lambda done: host.notice(*done))
    host.confirm(f'Export Add-On{"s" if plural else ""} Too?',
                 f'{message} They need {names} to play. Export {"those" if plural else "it"} as well?', 'Export', run)

