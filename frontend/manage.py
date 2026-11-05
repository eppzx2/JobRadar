import sqlite3

import streamlit as st

from database.store import set_option, setting
from matching.jobs import clean_url, folded
from notifications.telegram import configured


def source_form(db, row=None):
    key = str(row['id']) if row else 'add'
    with st.form('source-' + key, clear_on_submit=not row):
        name = st.text_input('Company or job board', row['name'] if row else '')
        url = st.text_input('Career page URL', row['url'] if row else '', placeholder='https://')
        enabled = st.checkbox('Enabled', bool(row['enabled']) if row else True)
        save = st.form_submit_button('Save changes' if row else 'Add source')
        remove = row and st.form_submit_button('Remove source')
    try:
        if remove:
            with db:
                db.execute('DELETE FROM sources WHERE id=?', (row['id'],))
            st.rerun()
        if save:
            if not name.strip():
                raise ValueError('Enter a company or board name.')
            values = (name.strip(), clean_url(url), int(enabled))
            with db:
                if row:
                    db.execute('UPDATE sources SET name=?,url=?,enabled=? WHERE id=?', (*values, row['id']))
                else:
                    db.execute('INSERT INTO sources(name,url,enabled) VALUES (?,?,?)', values)
            st.rerun()
    except (sqlite3.IntegrityError, ValueError) as exc:
        st.error('This URL is already configured.' if isinstance(exc, sqlite3.IntegrityError) else str(exc))


def sources(db):
    st.header('Sources management')
    with st.expander('Add a career page'):
        source_form(db)
    for row in db.execute('SELECT * FROM sources ORDER BY name COLLATE NOCASE'):
        with st.expander(f"{row['name']}  ·  {'Enabled' if row['enabled'] else 'Disabled'}"):
            source_form(db, row)


def keywords(db):
    st.header('Keyword management')
    st.caption('Choose IT and security role phrases. Matches also require a junior or internship title or employment type. Senior and data analytics titles are excluded.')
    scope = st.radio('Search in', ['Job titles', 'Job titles and descriptions'],
                     index=int(setting(db, 'descriptions')), horizontal=True)
    if (scope.endswith('descriptions')) != setting(db, 'descriptions'):
        set_option(db, 'descriptions', scope.endswith('descriptions'))
    with st.form('new-word', clear_on_submit=True):
        word = st.text_input('New keyword')
        add = st.form_submit_button('Add keyword')
    rows = db.execute('SELECT * FROM keywords ORDER BY folded').fetchall()
    edit = remove = False
    if rows:
        ids = {r['id']: r['word'] for r in rows}
        selected = st.selectbox('Edit a keyword', ids.keys(), format_func=ids.get)
        with st.form(f'edit-word-{selected}'):
            changed = st.text_input('Keyword', ids[selected])
            edit = st.form_submit_button('Save keyword')
            remove = st.form_submit_button('Remove keyword')
    try:
        if add or edit or remove:
            with db:
                if remove:
                    db.execute('DELETE FROM keywords WHERE id=?', (selected,))
                else:
                    value = (word if add else changed).strip()
                    if not value:
                        raise ValueError('Enter a keyword.')
                    if add:
                        db.execute('INSERT INTO keywords(word,folded) VALUES (?,?)', (value, folded(value)))
                    else:
                        db.execute('UPDATE keywords SET word=?,folded=? WHERE id=?', (value, folded(value), selected))
            st.rerun()
    except sqlite3.IntegrityError:
        st.error('This keyword already exists.')
    except ValueError as exc:
        st.error(str(exc))
    st.subheader('Active keywords')
    if rows:
        st.write(' · '.join(r['word'] for r in rows))
    else:
        st.caption('Add a keyword to see matching vacancies.')


def telegram(db):
    with st.sidebar.expander('Telegram notifications'):
        available = configured()
        if not available:
            st.caption('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file, then restart JobRadar.')
        active = st.toggle('Send new matches', value=setting(db, 'telegram'), disabled=not available)
        if active != setting(db, 'telegram'):
            set_option(db, 'telegram', active)
