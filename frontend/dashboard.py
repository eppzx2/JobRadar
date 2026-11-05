from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from database.store import as_job, setting
from frontend.manage import keywords, sources, telegram
from matching.jobs import matches
from scraper.http import FetchError
from scraper.workflow import fetch

VIEWS = ['All Matching Jobs', 'Newly Discovered Jobs', 'Previously Discovered Jobs',
         'Sources Management', 'Keyword Management']


def results(db, view, run):
    st.header(view)
    words = [r[0] for r in db.execute('SELECT word FROM keywords ORDER BY folded')]
    use_desc = setting(db, 'descriptions')
    rows = []
    for row in db.execute('SELECT * FROM jobs ORDER BY last_run DESC,id DESC'):
        hits = matches(as_job(row), words, use_desc)
        fresh = row['first_run'] == run
        if hits and (view != VIEWS[1] or fresh) and (view != VIEWS[2] or not fresh):
            rows.append(dict(row, hits=hits, fresh=fresh))
    with st.expander('Filter vacancies'):
        cols = st.columns(2)
        filters = {}
        for i, (key, label) in enumerate([('company', 'Company'), ('hits', 'Keyword'), ('location', 'Location'),
                                          ('employment', 'Employment type')]):
            values = {v for r in rows for v in (r[key] if key == 'hits' else [r[key] or 'Unspecified'])}
            filters[key] = cols[i % 2].multiselect(label, sorted(values), key=f'{view}-{key}')
        fresh_only = st.checkbox('New vacancies only', key=view+'fresh')
    for key, values in filters.items():
        if values:
            rows = [r for r in rows if set(values).intersection(r[key] if key == 'hits' else [r[key] or 'Unspecified'])]
    if fresh_only:
        rows = [r for r in rows if r['fresh']]
    if not rows:
        if run is None:
            st.info('Click Fetch Jobs to check your enabled career pages.')
        else:
            st.info('No saved vacancies match this view. Check your filters, keywords, or source results.')
        return
    st.caption(f'{len(rows)} matching vacancies in saved history')
    page = 1
    if len(rows) > 20:
        page = st.selectbox('Results page', range(1, (len(rows) + 19) // 20 + 1))
    for r in rows[(page-1)*20:page*20]:
        with st.container(border=True):
            st.caption(f"{r['company']}   ·   {'New' if r['fresh'] else 'Previously discovered'}")
            st.subheader(r['title'])
            st.write(' · '.join([r['location'] or 'Location unspecified', r['employment'] or 'Employment type unspecified',
                                 (r['published'] or 'Date unspecified')[:32]]))
            st.caption('Matched keywords  ·  ' + ', '.join(r['hits']))
            if r['last_run'] != run:
                st.caption('Saved from an earlier fetch. Check availability on the career page.')
            if r['description']:
                with st.expander('Job description'):
                    st.text(r['description'])
            if r['url']:
                st.link_button('View vacancy / apply ↗', r['url'])
            else:
                st.caption('Application link unavailable.')


def dashboard(db):
    st.set_page_config(page_title='JobRadar', page_icon='◎', layout='wide')
    st.sidebar.title('◎ JobRadar')
    view = st.sidebar.radio('Workspace', VIEWS, key='workspace_view', label_visibility='collapsed')
    telegram(db)
    top, action = st.columns([4, 1])
    top.title('Vacancy dashboard')
    if action.button('Fetch Jobs', type='primary', width="stretch"):
        with st.status('Fetching vacancies…', expanded=True) as status:
            try:
                fetch(db, status.write)
                status.update(label='Fetch completed', state='complete', expanded=False)
            except FetchError as exc:
                status.update(label=str(exc), state='error')
    last = db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    if last:
        when = datetime.fromisoformat(last['finished']).astimezone(ZoneInfo('Asia/Baku'))
        st.caption('Last fetch · ' + when.strftime('%d %b %Y, %H:%M') + ' (Baku)')
    else:
        st.caption('No fetches yet')
    new_count = db.execute('SELECT count(*) FROM jobs WHERE first_run=?', (last['id'],)).fetchone()[0] if last else None
    cols = st.columns(5)
    for col, field, label in zip(cols, ['checked', 'discovered', 'matched', 'new_total', 'fresh'],
                                 ['Sources checked', 'Vacancies discovered', 'Matching vacancies', 'New vacancies', 'New matches']):
        value = new_count if field == 'new_total' else last[field] if last else None
        col.metric(label, value if value is not None else '—', border=True)
    if last:
        checks = list(db.execute('SELECT * FROM checks WHERE run=?', (last['id'],)))
        issues = sum(r['status'] != 'Checked' for r in checks)
        with st.expander(f"Latest source results · {len(checks)-issues}/{len(checks)} checked successfully"):
            st.dataframe([{'Source': r['name'], 'Status': r['status'], 'Vacancies': r['count'], 'Details': r['message']}
                          for r in checks], hide_index=True, width="stretch")
            if last['notification']:
                st.caption(last['notification'])
    st.divider()
    if view == VIEWS[3]:
        sources(db)
    elif view == VIEWS[4]:
        keywords(db)
    else:
        results(db, view, last['id'] if last else None)
