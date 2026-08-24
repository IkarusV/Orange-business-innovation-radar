import reflex as rx

from radar_v2.pages.company import company
from radar_v2.pages.discovery import discovery
from radar_v2.pages.help import help_page
from radar_v2.pages.opportunities import opportunities
from radar_v2.pages.opportunity_detail import opportunity_detail
from radar_v2.pages.overview import overview
from radar_v2.pages.refresh import refresh
from radar_v2.pages.reports import reports
from radar_v2.pages.sources import sources
from radar_v2.pages.settings import settings_page
from radar_v2.state import RadarState


app = rx.App()
app.add_page(opportunity_detail, route="/opportunities/[opportunity_id]", title="Opportunity · Innovation Radar", on_load=RadarState.load_detail)
app.add_page(overview, route="/", title="Orange Business Innovation Radar", on_load=RadarState.load)
app.add_page(opportunities, route="/opportunities", title="Opportunities · Innovation Radar", on_load=RadarState.load)
app.add_page(company, route="/company", title="Company Workspace · Innovation Radar", on_load=RadarState.load)
app.add_page(sources, route="/sources", title="Sources · Innovation Radar", on_load=RadarState.load)
app.add_page(discovery, route="/discovery", title="Discovery · Innovation Radar", on_load=RadarState.load)
app.add_page(reports, route="/reports", title="Reports · Innovation Radar", on_load=RadarState.load)
app.add_page(refresh, route="/refresh", title="Radar Update · Innovation Radar", on_load=RadarState.load)
app.add_page(settings_page, route="/settings", title="Settings · Innovation Radar", on_load=RadarState.load)
app.add_page(help_page, route="/help", title="Help · Innovation Radar", on_load=RadarState.load)
