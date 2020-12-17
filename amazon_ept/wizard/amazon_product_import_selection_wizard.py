# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Added class and methods to import amazon product in odoo.
"""

import base64
import csv
from io import StringIO
from odoo import models, fields, _
from odoo.exceptions import UserError


class AmazonProductImportSelectionWizard(models.TransientModel):
    """
    Added class to import amazon product and also added methods to import and  read csv file,
    create amazon listing.
    """
    _name = "amazon.import.product.wizard"
    _description = 'amazon.import.product.wizard'

    seller_id = fields.Many2one('amazon.seller.ept', string='Seller',
                                help="Select Seller Account to associate with this Instance")
    file_name = fields.Char(string='Name')
    choose_file = fields.Binary(filename="filename")
    delimiter = fields.Selection([('tab', 'Tab'), ('semicolon', 'Semicolon'), ('comma', 'Comma')],
                                 string="Separator", default='comma')

    def download_sample_attachment(self):
        """
        This Method relocates download sample file of amazon.
        :return: This Method return file download file.
        """
        attachment = self.env['ir.attachment'].search([('name', '=', 'import_product_sample.csv')])
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % (attachment.id),
            'target': 'new',
            'nodestroy': False,
        }

    def import_csv_file(self):
        """
        This Method relocates Import product csv in amazon listing and mapping of amazon product
        listing.
        :return:
        """
        if not self.choose_file or not self.seller_id:
            raise UserError(_('Please Select Seller and Upload File.'))

        self.read_import_csv_file()
        if self.choose_file and self.seller_id:
            csv_file = StringIO(base64.b64decode(self.choose_file).decode())
            file_write = open('/tmp/products.csv', 'w+')
            file_write.writelines(csv_file.getvalue())
            file_write.close()

            product_obj = self.env["product.product"]
            amazon_product_ept_obj = self.env['amazon.product.ept']
            instance_dict = {}
            if self.delimiter == "tab":
                reader = csv.DictReader(open('/tmp/products.csv', "rU"), delimiter="\t")
            elif self.delimiter == "semicolon":
                reader = csv.DictReader(open('/tmp/products.csv', "rU"), delimiter=";")
            else:
                reader = csv.DictReader(open('/tmp/products.csv', "rU"), delimiter=",")
            if reader:
                if reader.fieldnames and len(reader.fieldnames) == 5:
                    for line in reader:
                        amazon_product_name = line.get('Title')
                        odoo_default_code = line.get('Internal Reference')
                        seller_sku = line.get('Seller SKU')
                        amazon_marketplace = line.get('Marketplace')
                        fulfillment = line.get('Fulfillment')
                        instance = False

                        if odoo_default_code:
                            product_id = product_obj.search(
                                ['|', ("default_code", "=", odoo_default_code),
                                 ("barcode", "=", odoo_default_code)], limit=1)

                            if not product_id:
                                odoo_product_dict = {
                                    'name': amazon_product_name,
                                    'default_code': odoo_default_code,
                                    'type': 'product'
                                }
                                product_id = product_obj.create(odoo_product_dict)

                            if amazon_marketplace:
                                instance = instance_dict.get(amazon_marketplace)
                                if not instance:
                                    instance = self.seller_id.instance_ids.filtered(
                                        lambda l: l.marketplace_id.name == amazon_marketplace)
                                    instance_dict.update({amazon_marketplace: instance})

                            if instance and fulfillment and seller_sku:
                                amazon_product_listing = amazon_product_ept_obj.search(
                                    [("seller_sku", "=", seller_sku),
                                     ("fulfillment_by", "=", fulfillment),
                                     ("instance_id", "=", instance.id)], limit=1)
                                if not amazon_product_listing:
                                    self.create_amazon_listing(amazon_product_ept_obj, product_id,
                                                               amazon_product_name, fulfillment,
                                                               seller_sku,
                                                               instance)
                    return {
                        'effect': {
                            'fadeout': 'slow',
                            'message': "All products import successfully!",
                            'img_url': '/web/static/src/img/smile.svg',
                            'type': 'rainbow_man',
                        }
                    }
                else:
                    raise UserError(_(
                        "Either file is invalid or proper delimiter/separator is not specified "
                        "or not found required fields."))
            else:
                raise UserError(_(
                    "Either file format is not csv or proper delimiter/separator is not specified"))
        else:
            raise UserError(_("Please Select File and/or choose Amazon Seller to Import Product"))

    def create_amazon_listing(self, amazon_product_ept_obj, product_obj, amazon_product_name,
                              fulfillment,
                              seller_sku, instance):
        """
        This Method relocates if product exist in odoo and product doesn't exist in amazon create
        amazon product listing.
        :param amazon_product_ept_obj: This arguments relocated browse object of amazon product
        listing.
        :param product_obj: This arguments relocates browse object of odoo product.
        :param amazon_product_name: This arguments relocates product name of amazon.
        :param fulfillment: This arguments relocates fulfillment of amazon.
        :param seller_sku: This arguments relocates seller sku of amazon product.
        :param instance: This arguments relocates instance of amazon.
        :return: This method return boolean(True/False).
        """
        amazon_product_ept_obj.create(
            {'name': amazon_product_name or product_obj.name,
             'fulfillment_by': fulfillment,
             'product_id': product_obj.id,
             'seller_sku': seller_sku,
             'instance_id': instance.id,
             'exported_to_amazon': True}
        )
        return True

    def read_import_csv_file(self):
        """
        This Method relocates read csv and check validation if seller sku doesn't exist in csv raise
         error.
        :return: This Method return boolean(True/False).
        """
        if self.choose_file:
            data = StringIO(base64.b64decode(self.choose_file).decode())

            if self.delimiter == "tab":
                reader = csv.DictReader(data, delimiter='\t')
            elif self.delimiter == "semicolon":
                reader = csv.DictReader(data, delimiter=';')
            else:
                reader = csv.DictReader(data, delimiter=',')
            seller_error_line = []

            next(reader)
            for line in reader:
                if not line.get('Seller SKU'):
                    seller_error_line.append(reader.line_num)
            message = ""
            if seller_error_line:
                message += 'File is invalid Seller SKU must be required field.'
            if message:
                raise UserError(_(message))
