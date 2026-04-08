#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRM Integration
Abstract layer for Salesforce, HubSpot, and other CRM systems
"""

import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)

class CRMConnector(ABC):
    """Abstract base class for CRM connectors"""
    
    @abstractmethod
    def create_contact(self, data: Dict) -> str:
        """Create contact in CRM"""
        pass
    
    @abstractmethod
    def update_contact(self, contact_id: str, data: Dict):
        """Update contact in CRM"""
        pass
    
    @abstractmethod
    def create_deal(self, data: Dict) -> str:
        """Create deal/opportunity in CRM"""
        pass
    
    @abstractmethod
    def update_deal_stage(self, deal_id: str, stage: str):
        """Update deal stage"""
        pass
    
    @abstractmethod
    def add_note(self, contact_id: str, note: str):
        """Add note to contact"""
        pass


class SalesforceConnector(CRMConnector):
    """Salesforce CRM connector"""
    
    def __init__(self, api_key: str, instance_url: str):
        """
        Initialize Salesforce connector
        
        Args:
            api_key: Salesforce API key
            instance_url: Salesforce instance URL
        """
        self.api_key = api_key
        self.instance_url = instance_url
        
        try:
            from simple_salesforce import Salesforce
            self.sf = Salesforce(
                instance_url=instance_url,
                session_id=api_key
            )
            logger.info("Salesforce connector initialized")
        except ImportError:
            logger.error("simple-salesforce not installed")
            self.sf = None
        except Exception as e:
            logger.error(f"Error initializing Salesforce: {e}")
            self.sf = None
    
    def create_contact(self, data: Dict) -> str:
        """Create contact in Salesforce"""
        if not self.sf:
            return None
        
        try:
            contact_data = {
                'FirstName': data.get('first_name', ''),
                'LastName': data.get('last_name', data.get('name', 'Unknown')),
                'Email': data.get('email'),
                'Phone': data.get('phone'),
                'MailingStreet': data.get('address'),
                'LeadSource': 'Sales Bot'
            }
            
            result = self.sf.Contact.create(contact_data)
            contact_id = result['id']
            
            logger.info(f"Created Salesforce contact: {contact_id}")
            return contact_id
            
        except Exception as e:
            logger.error(f"Error creating Salesforce contact: {e}")
            return None
    
    def update_contact(self, contact_id: str, data: Dict):
        """Update contact in Salesforce"""
        if not self.sf:
            return
        
        try:
            self.sf.Contact.update(contact_id, data)
            logger.info(f"Updated Salesforce contact: {contact_id}")
        except Exception as e:
            logger.error(f"Error updating Salesforce contact: {e}")
    
    def create_deal(self, data: Dict) -> str:
        """Create opportunity in Salesforce"""
        if not self.sf:
            return None
        
        try:
            opp_data = {
                'Name': data.get('name', 'Sales Bot Deal'),
                'StageName': 'Prospecting',
                'CloseDate': data.get('close_date', datetime.now().strftime('%Y-%m-%d')),
                'Amount': data.get('amount'),
                'ContactId': data.get('contact_id'),
                'LeadSource': 'Sales Bot'
            }
            
            result = self.sf.Opportunity.create(opp_data)
            deal_id = result['id']
            
            logger.info(f"Created Salesforce opportunity: {deal_id}")
            return deal_id
            
        except Exception as e:
            logger.error(f"Error creating Salesforce opportunity: {e}")
            return None
    
    def update_deal_stage(self, deal_id: str, stage: str):
        """Update opportunity stage"""
        if not self.sf:
            return
        
        try:
            self.sf.Opportunity.update(deal_id, {'StageName': stage})
            logger.info(f"Updated Salesforce opportunity {deal_id} to {stage}")
        except Exception as e:
            logger.error(f"Error updating Salesforce opportunity: {e}")
    
    def add_note(self, contact_id: str, note: str):
        """Add note to contact"""
        if not self.sf:
            return
        
        try:
            note_data = {
                'ParentId': contact_id,
                'Title': 'Sales Bot Note',
                'Body': note
            }
            
            self.sf.Note.create(note_data)
            logger.info(f"Added note to Salesforce contact: {contact_id}")
        except Exception as e:
            logger.error(f"Error adding Salesforce note: {e}")


class HubSpotConnector(CRMConnector):
    """HubSpot CRM connector"""
    
    def __init__(self, api_key: str):
        """
        Initialize HubSpot connector
        
        Args:
            api_key: HubSpot API key
        """
        self.api_key = api_key
        
        try:
            from hubspot import HubSpot
            self.hs = HubSpot(access_token=api_key)
            logger.info("HubSpot connector initialized")
        except ImportError:
            logger.error("hubspot-api-client not installed")
            self.hs = None
        except Exception as e:
            logger.error(f"Error initializing HubSpot: {e}")
            self.hs = None
    
    def create_contact(self, data: Dict) -> str:
        """Create contact in HubSpot"""
        if not self.hs:
            return None
        
        try:
            properties = {
                'firstname': data.get('first_name', ''),
                'lastname': data.get('last_name', data.get('name', 'Unknown')),
                'email': data.get('email'),
                'phone': data.get('phone'),
                'address': data.get('address'),
                'hs_lead_status': 'NEW'
            }
            
            contact = self.hs.crm.contacts.basic_api.create(
                simple_public_object_input={'properties': properties}
            )
            
            contact_id = contact.id
            logger.info(f"Created HubSpot contact: {contact_id}")
            return contact_id
            
        except Exception as e:
            logger.error(f"Error creating HubSpot contact: {e}")
            return None
    
    def update_contact(self, contact_id: str, data: Dict):
        """Update contact in HubSpot"""
        if not self.hs:
            return
        
        try:
            self.hs.crm.contacts.basic_api.update(
                contact_id=contact_id,
                simple_public_object_input={'properties': data}
            )
            logger.info(f"Updated HubSpot contact: {contact_id}")
        except Exception as e:
            logger.error(f"Error updating HubSpot contact: {e}")
    
    def create_deal(self, data: Dict) -> str:
        """Create deal in HubSpot"""
        if not self.hs:
            return None
        
        try:
            properties = {
                'dealname': data.get('name', 'Sales Bot Deal'),
                'dealstage': 'appointmentscheduled',
                'amount': data.get('amount'),
                'closedate': data.get('close_date'),
                'pipeline': 'default'
            }
            
            deal = self.hs.crm.deals.basic_api.create(
                simple_public_object_input={'properties': properties}
            )
            
            deal_id = deal.id
            logger.info(f"Created HubSpot deal: {deal_id}")
            return deal_id
            
        except Exception as e:
            logger.error(f"Error creating HubSpot deal: {e}")
            return None
    
    def update_deal_stage(self, deal_id: str, stage: str):
        """Update deal stage"""
        if not self.hs:
            return
        
        try:
            self.hs.crm.deals.basic_api.update(
                deal_id=deal_id,
                simple_public_object_input={'properties': {'dealstage': stage}}
            )
            logger.info(f"Updated HubSpot deal {deal_id} to {stage}")
        except Exception as e:
            logger.error(f"Error updating HubSpot deal: {e}")
    
    def add_note(self, contact_id: str, note: str):
        """Add note to contact"""
        if not self.hs:
            return
        
        try:
            note_data = {
                'hs_note_body': note,
                'hs_timestamp': datetime.now().isoformat()
            }
            
            self.hs.crm.objects.notes.basic_api.create(
                simple_public_object_input={'properties': note_data}
            )
            
            # Associate note with contact
            # (requires additional API call)
            
            logger.info(f"Added note to HubSpot contact: {contact_id}")
        except Exception as e:
            logger.error(f"Error adding HubSpot note: {e}")


class CRMManager:
    """Manage CRM integration"""
    
    def __init__(self, config):
        """
        Initialize CRM manager
        
        Args:
            config: Config instance
        """
        self.config = config
        self.connector = self._initialize_connector()
    
    def _initialize_connector(self) -> Optional[CRMConnector]:
        """Initialize CRM connector based on config"""
        crm_provider = getattr(self.config, 'CRM_PROVIDER', None)
        
        if crm_provider == 'salesforce':
            api_key = getattr(self.config, 'SALESFORCE_API_KEY', None)
            instance_url = getattr(self.config, 'SALESFORCE_INSTANCE_URL', None)
            
            if api_key and instance_url:
                return SalesforceConnector(api_key, instance_url)
        
        elif crm_provider == 'hubspot':
            api_key = getattr(self.config, 'HUBSPOT_API_KEY', None)
            
            if api_key:
                return HubSpotConnector(api_key)
        
        logger.warning(f"CRM not configured or unknown provider: {crm_provider}")
        return None
    
    def sync_customer(self, customer_data: Dict) -> Optional[str]:
        """
        Sync customer to CRM
        
        Args:
            customer_data: Customer data
            
        Returns:
            CRM contact ID or None
        """
        if not self.connector:
            return None
        
        # Check if contact exists (by email or phone)
        # For now, always create new
        
        contact_id = self.connector.create_contact(customer_data)
        return contact_id
    
    def sync_order(self, order_data: Dict, contact_id: str = None) -> Optional[str]:
        """
        Sync order to CRM as deal
        
        Args:
            order_data: Order data
            contact_id: CRM contact ID
            
        Returns:
            CRM deal ID or None
        """
        if not self.connector:
            return None
        
        deal_data = {
            'name': f"Order #{order_data.get('order_id', 'N/A')}",
            'amount': order_data.get('total'),
            'contact_id': contact_id,
            'close_date': datetime.now().strftime('%Y-%m-%d')
        }
        
        deal_id = self.connector.create_deal(deal_data)
        return deal_id
    
    def update_deal_status(self, deal_id: str, status: str):
        """Update deal status based on order status"""
        if not self.connector:
            return
        
        # Map order status to CRM stage
        stage_map = {
            'pending': 'Prospecting',
            'confirmed': 'Qualification',
            'completed': 'Closed Won',
            'cancelled': 'Closed Lost'
        }
        
        stage = stage_map.get(status, 'Prospecting')
        self.connector.update_deal_stage(deal_id, stage)
    
    def log_interaction(self, contact_id: str, interaction: str):
        """Log customer interaction"""
        if not self.connector:
            return
        
        note = f"[Sales Bot] {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{interaction}"
        self.connector.add_note(contact_id, note)
