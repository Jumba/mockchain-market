from PyQt5 import QtWidgets


class BanksPortfolioController:
    def __init__(self, mainwindow):
        self.mainwindow = mainwindow
        self.mortgages_table = self.mainwindow.fip_campaigns_table

    def setup_view(self):
        # Clear table
        self.mortgages_table.setRowCount(0)

        # Getting the mortgages from the bank
        mortgages = self.mainwindow.api.load_mortgages(self.mainwindow.app.user)

        # If the list is empty, do nothing. Otherwise fill table
        if mortgages:
            # Fill the mortgage table
            for [mortgage, house, campaign] in mortgages:
                # Property Address, Campaign Status, Investment Status, Amount Invested, Interest, Duration
                address = house.address + ' ' + house.house_number + ', ' + house.postal_code

                campaign_status = ''
                if campaign.completed:
                    campaign_status = 'Completed'
                else:
                    campaign_status = 'Running'

                row_count = self.mortgages_table.rowCount()
                self.mortgages_table.insertRow(row_count)
                self.mortgages_table.setItem(row_count, 0, QtWidgets.QTableWidgetItem(address))
                self.mortgages_table.setItem(row_count, 1, QtWidgets.QTableWidgetItem(campaign_status))
                self.mortgages_table.setItem(row_count, 3, QtWidgets.QTableWidgetItem(str(mortgage.amount)))
                self.mortgages_table.setItem(row_count, 4, QtWidgets.QTableWidgetItem(str(mortgage.interest_rate)))
                self.mortgages_table.setItem(row_count, 5, QtWidgets.QTableWidgetItem(str(mortgage.default_rate)))
                self.mortgages_table.setItem(row_count, 6, QtWidgets.QTableWidgetItem(str(mortgage.duration)))
