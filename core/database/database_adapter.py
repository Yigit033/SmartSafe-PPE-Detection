#!/usr/bin/env python3
"""
Database Adapter - PostgreSQL Support
Handles production PostgreSQL database connections and operations.
"""

import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import uuid
import secrets
import time
import traceback
import threading
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database configuration"""
    database_url: str
    connection_params: Dict[str, Any]


def _normalize_company_ppe_requirements_list(
    items: Any, sector: Optional[str] = None
) -> Optional[List[str]]:
    """DB/UI listesini `backend/company/sector_config.ts` id'leriyle hizalar.

    - mandatory:false olanlar çıkarılır.
    - ID'ler TS'deki gibi kalır (hairnet, apron, face_mask, …); model sınıf adlarına
      çevirme detection katmanında yapılır (bkz. sector_ppe_config.map_sh17_…).
    - Sektör biliniyorsa, yalnızca o sektör şablonunda tanımlı id'ler tutulur;
      hiçbiri eşleşmezse (eski/özel veri) liste olduğu gibi bırakılır.
    """
    if items is None:
        return None
    if not isinstance(items, list):
        return None
    if len(items) == 0:
        return []

    # Lazy import: database_adapter çok erken yüklenebilir
    from sector.sector_ppe_config import get_all_ppe_ids_for_sector, resolve_sector_config_key

    out: List[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict):
            pid = item.get("id") or item.get("ppe_type") or item.get("type")
            if pid is None:
                continue
            if item.get("mandatory") is False:
                continue
            out.append(str(pid).strip().lower())
        else:
            s = str(item).strip().lower()
            if s:
                out.append(s)

    seen = set()
    result: List[str] = []
    for pid in out:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)

    if sector:
        sk = resolve_sector_config_key(sector)
        allowed = get_all_ppe_ids_for_sector(sk)
        if allowed:
            filtered = [x for x in result if x in allowed]
            if filtered:
                return filtered
    return result


class DatabaseAdapter:
    """Database adapter for PostgreSQL"""
    
    def __init__(self):
        self.config = self._get_database_config()
        self.db_type = 'postgresql'
        self.connection_pool = None
        self._init_connection_pool()
        logger.info("🗄️ Database adapter initialized: postgresql")

    def get_placeholder(self) -> str:
        """Parametre placeholder'ı (Daima PostgreSQL %s)."""
        return "%s"

    def _init_connection_pool(self):
        """Initialize connection pool for PostgreSQL"""
        try:
            database_url = self.config.database_url
            if not database_url:
                logger.warning("⚠️ DATABASE_URL not set, skipping connection pool")
                return

            # Handle potential issues with postgresql:// vs postgres://
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
                
            parsed = urlparse(database_url)
            
            try:
                minconn = max(1, int(os.getenv("DB_POOL_MINCONN", "5")))
                maxconn = max(minconn, int(os.getenv("DB_POOL_MAXCONN", "100")))
            except ValueError:
                minconn, maxconn = 5, 100

            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                host=parsed.hostname,
                port=parsed.port or 5432,
                database=parsed.path[1:],
                user=parsed.username,
                password=parsed.password,
                connect_timeout=10
            )
            logger.info(f"✅ PostgreSQL threaded connection pool initialized ({minconn}-{maxconn})")
        except Exception as e:
            logger.warning(f"⚠️ Connection pool initialization failed: {e}, will use direct connections")
    
    def _get_database_config(self) -> DatabaseConfig:
        """Get database configuration based on environment"""
        try:
            # Check for PostgreSQL configuration first
            database_url = (os.getenv("DATABASE_URL") or "").strip()
            if database_url and "your_project_id" in database_url.replace(" ", ""):
                logger.warning(
                    "DATABASE_URL looks like a Supabase template placeholder (your_project_id); "
                    "set a real URL or local Docker URL (see infra/docker-compose.infra-only.yml)."
                )
                database_url = ""
            if database_url and (database_url.startswith('postgresql://') or database_url.startswith('postgres://')):
                logger.info("✅ PostgreSQL configuration found")
                return DatabaseConfig(
                    database_url=database_url,
                    connection_params={'database_url': database_url}
                )
            
            # Fallback to database_config.py for discrete params
            try:
                from database.database_config import db_config as config
                if config.host:
                    url = config.get_connection_string()
                    return DatabaseConfig(
                        database_url=url,
                        connection_params={'database_url': url}
                    )
            except ImportError:
                pass
                
            raise ValueError("No database configuration found (DATABASE_URL missing).")
        except Exception as e:
            logger.error(f"❌ Database config error: {e}")
            raise
    
    def health_check(self) -> bool:
        """Lightweight health check (SELECT 1) to verify DB connectivity.

        Used by ensure_database_initialized() to detect dead connections after long idle periods.
        """
        conn = None
        try:
            conn = self.get_connection(timeout=5)
            if not conn: return False
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            return True
        except Exception as e:
            logger.warning(f"⚠️ Database health check failed: {e}")
            return False
        finally:
            try:
                if conn is not None:
                    self.close_connection(conn)
            except Exception:
                pass
    
    def close_connection(self, conn):
        """Close PostgreSQL connection and return to pool if applicable"""
        try:
            if conn is None:
                return
            
            if self.connection_pool:
                try:
                    self.connection_pool.putconn(conn)
                    logger.debug("✅ Connection returned to pool")
                except Exception:
                    try:
                        conn.close()
                    except:
                        pass
            else:
                try:
                    conn.close()
                except:
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Error closing connection: {e}")
    
    def get_connection(self, timeout: int = 30):
        """Get database connection with thread safety and connection pooling"""
        try:
            # PostgreSQL
            # Try to use connection pool first
                if self.connection_pool:
                    try:
                        conn = self.connection_pool.getconn()
                        logger.debug("✅ Got connection from pool")
                        return conn
                    except Exception as pool_error:
                        logger.warning(f"⚠️ Connection pool error: {pool_error}, using direct connection")
                    try:
                        conn = self.connection_pool.getconn()
                        logger.debug("✅ Got connection from pool")
                        return conn
                    except Exception as pool_error:
                        logger.warning(f"⚠️ Connection pool error: {pool_error}, using direct connection")
                
                # Fallback to direct connection via secure connector
                # Fallback to direct connection
                database_url = self.config.database_url
                if database_url:
                    try:
                        # Handle potential issues with postgresql:// vs postgres://
                        if database_url.startswith('postgres://'):
                            database_url = database_url.replace('postgres://', 'postgresql://', 1)
                            
                        logger.info("🔌 Attempting direct psycopg2 connection as fallback")
                        conn = psycopg2.connect(database_url, connect_timeout=10)
                        return conn
                    except Exception as direct_err:
                        logger.warning(f"⚠️ Direct PostgreSQL connection failed: {direct_err}")
                
                logger.warning("⚠️ No database configuration available for connection")
                return None
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            return None
    
    def init_database(self) -> bool:
        """
        DATABASE INITIALIZATION (Managed by Encore Migrations)
        In production, schema is managed ONLY by Encore Migrations.
        This method performs health check and waits for all critical tables.
        """
        try:
            logger.info("🔍 Checking database readiness and migrations...")
            
            # 1. Wait for DB server to be reachable
            max_db_retries = 20
            for attempt in range(max_db_retries):
                if self.health_check():
                    break
                logger.warning(f"⏳ Waiting for database connection... ({attempt+1}/{max_db_retries})")
                time.sleep(3)
            else:
                logger.error("❌ Database server not reachable.")
                return False

            # 2. Wait for Encore Migrations to create all critical tables
            critical_tables = ['companies', 'cameras', 'users', 'camera_schedules']
            max_migration_retries = 30 # Wait longer for migrations
            
            for attempt in range(max_migration_retries):
                conn = self.get_connection()
                if not conn:
                    time.sleep(2)
                    continue
                
                try:
                    cursor = conn.cursor()
                    missing_tables = []
                    
                    for table in critical_tables:
                        cursor.execute("""
                            SELECT count(*) FROM information_schema.tables 
                            WHERE table_schema = 'public' AND table_name = %s
                        """, (table,))
                        if cursor.fetchone()[0] == 0:
                            missing_tables.append(table)
                    
                    if not missing_tables:
                        # All tables exist
                        conn.commit()
                        logger.info("✅ Database schema verified (all tables present). AI Core is ready.")
                        return True
                    else:
                        logger.warning(f"⏳ Waiting for migrations... Missing tables: {', '.join(missing_tables)} (Attempt {attempt+1}/{max_migration_retries})")
                        time.sleep(5)
                finally:
                    self.close_connection(conn)
            
            logger.error("❌ Database migrations did not complete in time.")
            return False
                
        except Exception as e:
            logger.error(f"❌ Database initialization check failed: {e}")
            return False

    
    def execute_query(
        self,
        query: str,
        params: tuple = None,
        fetch_all: bool = True,
        fetch_one: bool = False,
    ) -> Any:
        """Execute database query with improved error handling and retry logic.
        
        Contract:
        - For SELECT:
          - fetch_one=True  -> returns single row as dict (or None)
          - fetch_all=True  -> returns list[dict] (possibly empty)
          - fetch_all=False -> returns single row as dict (or None)  (legacy behavior)
        - For INSERT/UPDATE/DELETE: returns cursor.rowcount (int)
        
        Notes:
        - fetch_one takes precedence over fetch_all to avoid ambiguous calls.
        """
        max_retries = 3
        retry_delay = 0.1  # 100ms

        # Normalize flags (fetch_one wins).
        if fetch_one:
            fetch_all = False
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                if conn is None:
                    logger.error("❌ Database connection failed")
                    return None
                
                cursor = conn.cursor()
            
                # Execute query
                # Compatibility: Convert '?' placeholders to PostgreSQL '%s' style
                if '?' in query:
                    query = query.replace('?', '%s')
                    logger.debug(f"🔄 Converted query to PostgreSQL style: {query}")
                
                cursor.execute(query, params or ())
                    
                # Handle different query types
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    result = cursor.rowcount
                    conn.commit()
                    logger.debug(f"✅ Query executed successfully: {result} rows affected")
                    return result
                else:  # SELECT queries
                    if fetch_all:
                        result = cursor.fetchall()
                    else:
                        result = cursor.fetchone()
                    
                    # Check if result is empty
                    if not result:
                        logger.debug(f"ℹ️ Query returned no results")
                        return None if not fetch_all else []
                    
                    # Convert to list of dictionaries for better handling
                    try:
                        # Check if cursor.description exists (for SELECT queries)
                        if not cursor.description:
                            logger.warning(f"⚠️ No cursor description available")
                            return None if not fetch_all else []
                        
                        columns = [description[0] for description in cursor.description]
                        if fetch_all:
                            if isinstance(result, list) and len(result) > 0:
                                result = [dict(zip(columns, row)) for row in result]
                            else:
                                result = []
                        else:
                            # Single result - convert to dict
                            if isinstance(result, (tuple, list)):
                                result = dict(zip(columns, result))
                            elif hasattr(result, 'keys'):  # Already a dict-like object (PostgreSQL RealDictRow)
                                result = dict(result)
                            else:
                                result = dict(zip(columns, [result]))
                        
                        logger.debug(f"✅ Query executed successfully: {len(result) if isinstance(result, list) else 1} rows returned")
                        return result
                    except Exception as convert_error:
                        logger.error(f"❌ Result conversion error: {convert_error}")
                        return None if not fetch_all else []
                    
            except psycopg2.Error as e:
                logger.error(f"❌ PostgreSQL query error: {e}")
                logger.error(f"❌ Query traceback: {traceback.format_exc()}")
                if conn:
                    conn.rollback()
                return None
            except Exception as e:
                logger.error(f"❌ General database query error: {e}")
                logger.error(f"❌ Query traceback: {traceback.format_exc()}")
                return None
            finally:
                # RELEASE CONNECTION TO POOL OR CLOSE IT
                if conn:
                    try:
                        self.close_connection(conn)
                    except Exception as e:
                        logger.warning(f"⚠️ Error releasing connection: {e}")

        logger.error(f"❌ Database query failed after {max_retries} attempts")
        return None



    # DVR System Methods
    def add_dvr_system(self, company_id: str, dvr_data: Dict[str, Any]) -> Optional[str]:
        """Add DVR system to database.

        (company_id, ip_address) is unique. If a soft-deleted row exists for that IP,
        restore it in place and return the existing ``dvr_id`` (preserves channel_ids
        and violation_events FKs). Otherwise insert and return the new ``dvr_id``.
        Returns None on failure.
        """
        try:
            logger.info(f"🔧 Adding DVR system: {dvr_data.get('name')} for company: {company_id}")

            existing = self.execute_query(
                """
                SELECT dvr_id, status FROM dvr_systems
                WHERE company_id = %s AND ip_address = %s
                """,
                (company_id, dvr_data["ip_address"]),
                fetch_one=True,
            )
            if existing:
                existing_id = existing["dvr_id"]
                status = (existing.get("status") or "").lower()
                if status == "deleted":
                    update_q = """
                        UPDATE dvr_systems SET
                            name = %s, port = %s, username = %s, password = %s,
                            dvr_type = %s, protocol = %s, api_path = %s, rtsp_port = %s,
                            max_channels = %s, status = %s, updated_at = NOW()
                        WHERE company_id = %s AND dvr_id = %s
                    """
                    upd_params = (
                        dvr_data["name"],
                        dvr_data.get("port", 80),
                        dvr_data.get("username", "admin"),
                        dvr_data.get("password", ""),
                        dvr_data.get("dvr_type", "generic"),
                        dvr_data.get("protocol", "http"),
                        dvr_data.get("api_path", "/api"),
                        dvr_data.get("rtsp_port", 554),
                        dvr_data.get("max_channels", 16),
                        "active",
                        company_id,
                        existing_id,
                    )
                    result = self.execute_query(update_q, upd_params, fetch_all=False)
                    if result is None or result <= 0:
                        logger.error(
                            f"❌ DVR restore failed: {dvr_data.get('name')} rowcount={result}"
                        )
                        return None
                    ch_q = """
                        UPDATE dvr_channels
                        SET status = 'inactive', updated_at = NOW()
                        WHERE company_id = %s AND dvr_id = %s AND status = 'deleted'
                    """
                    self.execute_query(ch_q, (company_id, existing_id), fetch_all=False)
                    logger.info(
                        f"✅ DVR system restored from soft-delete: {existing_id} "
                        f"({dvr_data.get('name')})"
                    )
                    return existing_id
                if existing_id != dvr_data.get("dvr_id"):
                    logger.warning(
                        "⚠️ Bu şirket için bu IP ile kayıtlı bir DVR zaten var; "
                        f"company_id={company_id} ip={dvr_data.get('ip_address')}"
                    )
                    return None
                logger.info(
                    f"ℹ️ DVR zaten kayıtlı (aynı dvr_id ve IP): {existing_id}"
                )
                return existing_id

            query = '''
                INSERT INTO dvr_systems (
                    dvr_id, company_id, name, ip_address, port, username, password,
                    dvr_type, protocol, api_path, rtsp_port, max_channels, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''

            params = (
                dvr_data['dvr_id'],
                company_id,
                dvr_data['name'],
                dvr_data['ip_address'],
                dvr_data.get('port', 80),
                dvr_data.get('username', 'admin'),
                dvr_data.get('password', ''),
                dvr_data.get('dvr_type', 'generic'),
                dvr_data.get('protocol', 'http'),
                dvr_data.get('api_path', '/api'),
                dvr_data.get('rtsp_port', 554),
                dvr_data.get('max_channels', 16),
                'active'
            )

            logger.info(f"🔧 SQL Query: {query}")
            logger.info(f"🔧 Parameters: {params}")

            result = self.execute_query(query, params, fetch_all=False)
            logger.info(f"🔧 Query result: {result}")

            if result is not None and result > 0:
                logger.info(f"✅ DVR system added successfully: {dvr_data.get('name')}")
                return dvr_data["dvr_id"]
            logger.error(
                f"❌ DVR system add failed: {dvr_data.get('name')} - rowcount: {result}"
            )
            return None

        except Exception as e:
            logger.error(f"❌ Add DVR system error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return None
    
    def get_dvr_systems(self, company_id: str) -> List[Dict[str, Any]]:
        """Get all DVR systems for a company"""
        try:
            query = '''
                SELECT * FROM dvr_systems 
                WHERE company_id = %s AND status <> 'deleted'
                ORDER BY created_at DESC
            '''
            
            result = self.execute_query(query, (company_id,))
            if result:
                logger.info(f"✅ Retrieved {len(result)} DVR systems for company {company_id}")
            return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR systems error: {e}")
            return []
    
    def get_dvr_system(self, company_id: str, dvr_id: str) -> Optional[Dict[str, Any]]:
        """Get specific DVR system"""
        try:
            query = '''
                SELECT * FROM dvr_systems 
                WHERE company_id = %s AND dvr_id = %s AND status <> 'deleted'
            '''
            
            result = self.execute_query(query, (company_id, dvr_id), fetch_all=False)
            if result:
                logger.info(f"✅ Retrieved DVR system: {dvr_id}")
                return result
            return None
            
        except Exception as e:
            logger.error(f"❌ Get DVR system error: {e}")
            return None
    
    def update_dvr_system(self, company_id: str, dvr_id: str, dvr_data: Dict[str, Any]) -> bool:
        """Update DVR system"""
        try:
            new_ip = dvr_data.get("ip_address")
            if new_ip:
                conflict = self.execute_query(
                    """
                    SELECT dvr_id FROM dvr_systems
                    WHERE company_id = %s AND ip_address = %s AND dvr_id <> %s
                      AND status <> 'deleted'
                    """,
                    (company_id, new_ip, dvr_id),
                    fetch_one=True,
                )
                if conflict:
                    logger.warning(
                        "⚠️ Bu şirket için bu IP başka bir DVR kaydında kullanılıyor; "
                        f"company_id={company_id} ip={new_ip}"
                    )
                    return False

            query = '''
                UPDATE dvr_systems 
                SET name = %s, ip_address = %s, port = %s, username = %s, password = %s,
                    dvr_type = %s, protocol = %s, api_path = %s, rtsp_port = %s, 
                    max_channels = %s, status = %s, updated_at = NOW()
                WHERE company_id = %s AND dvr_id = %s
            '''
            
            params = (
                dvr_data.get('name'),
                dvr_data.get('ip_address'),
                dvr_data.get('port', 80),
                dvr_data.get('username', 'admin'),
                dvr_data.get('password', ''),
                dvr_data.get('dvr_type', 'generic'),
                dvr_data.get('protocol', 'http'),
                dvr_data.get('api_path', '/api'),
                dvr_data.get('rtsp_port', 554),
                dvr_data.get('max_channels', 16),
                dvr_data.get('status', 'active'),
                company_id,
                dvr_id
            )
            
            result = self.execute_query(query, params, fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Update DVR system error: {e}")
            return False
    
    def delete_dvr_system(self, company_id: str, dvr_id: str) -> bool:
        """Soft-delete DVR system and related channels.

        This must not hard-delete because violation_events may reference dvr_channels.
        """
        try:
            # Mark channels deleted first (keeps FK integrity for violation_events)
            channel_query = '''
                UPDATE dvr_channels
                SET status = 'deleted', updated_at = NOW()
                WHERE company_id = %s AND dvr_id = %s AND status <> 'deleted'
            '''
            self.execute_query(channel_query, (company_id, dvr_id), fetch_all=False)

            # Mark DVR system deleted
            dvr_query = '''
                UPDATE dvr_systems
                SET status = 'deleted', updated_at = NOW()
                WHERE company_id = %s AND dvr_id = %s AND status <> 'deleted'
            '''
            result = self.execute_query(dvr_query, (company_id, dvr_id), fetch_all=False)

            # Streams are ephemeral; safe to hard-delete
            stream_query = '''
                DELETE FROM dvr_streams
                WHERE company_id = %s AND dvr_id = %s
            '''
            self.execute_query(stream_query, (company_id, dvr_id), fetch_all=False)

            logger.info(f"✅ DVR system soft-deleted: {dvr_id}")
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Delete DVR system error: {e}")
            return False
    
    # DVR Channel Methods
    def delete_dvr_channel(self, company_id: str, dvr_id: str, channel_id: str) -> bool:
        """Soft-delete a DVR channel (keeps violation_events history)."""
        try:
            query = '''
                UPDATE dvr_channels
                SET status = 'deleted', updated_at = NOW()
                WHERE company_id = %s AND dvr_id = %s AND channel_id = %s AND status <> 'deleted'
            '''
            self.execute_query(query, (company_id, dvr_id, channel_id), fetch_all=False)
            logger.info(f"✅ DVR channel soft-deleted: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting DVR channel {channel_id}: {e}")
            return False

    def add_dvr_channel(self, company_id: str, dvr_id: str, channel_data: Dict[str, Any]) -> bool:
        """Add DVR channel to database"""
        try:
            from utils.redaction import redact_url
            logger.debug(f"🔧 Adding DVR channel: {channel_data.get('name')} for DVR: {dvr_id}")
            
            # Use INSERT OR REPLACE to handle conflicts
            query = '''
                INSERT INTO dvr_channels (
                    channel_id, dvr_id, company_id, name, channel_number,
                    status, resolution_width, resolution_height, fps, rtsp_path, http_path
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (channel_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    resolution_width = EXCLUDED.resolution_width,
                    resolution_height = EXCLUDED.resolution_height,
                    fps = EXCLUDED.fps,
                    rtsp_path = EXCLUDED.rtsp_path,
                    http_path = EXCLUDED.http_path,
                    updated_at = NOW()
            '''
            
            params = (
                channel_data['channel_id'],
                dvr_id,
                company_id,
                channel_data['name'],
                channel_data['channel_number'],
                channel_data.get('status', 'inactive'),
                channel_data.get('resolution_width', 1920),
                channel_data.get('resolution_height', 1080),
                channel_data.get('fps', 25),
                channel_data.get('rtsp_path', ''),
                channel_data.get('http_path', '')
            )
            
            logger.debug(f"🔧 Channel SQL Query: {query}")
            # Never log credentials/URLs verbatim (RTSP/HTTP may include user:pass)
            safe_params = list(params)
            if len(safe_params) >= 11:
                safe_params[9] = redact_url(str(safe_params[9]))   # rtsp_path
                safe_params[10] = redact_url(str(safe_params[10]))  # http_path
            logger.debug(f"🔧 Channel Parameters: {tuple(safe_params)}")
            
            result = self.execute_query(query, params, fetch_all=False)
            logger.debug(f"🔧 Channel Query result: {result}")
            
            if result is not None and result > 0:
                logger.info(f"✅ DVR channel added successfully: {channel_data.get('name')}")
                return True
            else:
                logger.error(f"❌ DVR channel add failed: {channel_data.get('name')} - rowcount: {result}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Add DVR channel error: {e}")
            import traceback
            logger.error(f"❌ Channel traceback: {traceback.format_exc()}")
            return False
    
    def get_dvr_channels(self, company_id: str, dvr_id: str) -> List[Dict[str, Any]]:
        """Get all channels for a DVR system"""
        try:
            query = '''
                SELECT * FROM dvr_channels 
                WHERE company_id = %s AND dvr_id = %s AND status <> 'deleted'
                ORDER BY channel_number
            '''
            
            result = self.execute_query(query, (company_id, dvr_id))
            if result:
                logger.info(f"✅ Retrieved {len(result)} channels for DVR {dvr_id}")
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR channels error: {e}")
            return []
    
    def update_dvr_channel_status(self, company_id: str, channel_id: str, status: str) -> bool:
        """Update DVR channel status"""
        try:
            query = '''
                UPDATE dvr_channels 
                SET status = %s, updated_at = NOW()
                WHERE company_id = %s AND channel_id = %s
            '''
            
            result = self.execute_query(query, (status, company_id, channel_id), fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Update DVR channel status error: {e}")
            return False
    
    # DVR Stream Methods
    def add_dvr_stream(self, company_id: str, dvr_id: str, channel_id: str, stream_url: str) -> bool:
        """Add active DVR stream"""
        try:
            stream_id = f"stream_{dvr_id}_{channel_id}_{int(datetime.now().timestamp())}"
            
            query = '''
                INSERT INTO dvr_streams (
                    stream_id, dvr_id, company_id, channel_id, stream_url, status
                ) VALUES (%s, %s, %s, %s, %s, %s)
            '''
            
            params = (stream_id, dvr_id, company_id, channel_id, stream_url, 'active')
            
            result = self.execute_query(query, params, fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Add DVR stream error: {e}")
            return False
    
    def update_dvr_stream_status(self, company_id: str, stream_id: str, status: str, fps: float = 0) -> bool:
        """Update DVR stream status"""
        try:
            query = '''
                UPDATE dvr_streams 
                SET status = %s, fps = %s, updated_at = NOW()
                WHERE company_id = %s AND stream_id = %s
            '''
            
            result = self.execute_query(query, (status, fps, company_id, stream_id), fetch_all=False)
            return result is not None
            
        except Exception as e:
            logger.error(f"❌ Update DVR stream status error: {e}")
            return False
    
    def get_active_dvr_streams(self, company_id: str) -> List[Dict[str, Any]]:
        """Get active DVR streams for a company"""
        try:
            query = '''
                SELECT * FROM dvr_streams 
                WHERE company_id = %s AND status = 'active'
                ORDER BY start_time DESC
            '''
            
            result = self.execute_query(query, (company_id,))
            if result:
                logger.info(f"✅ Retrieved {len(result)} active streams for company {company_id}")
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get active DVR streams error: {e}")
            return []

    # DVR Detection Results Methods
    def add_dvr_detection_result(self, result_data: Dict[str, Any]) -> bool:
        """Add DVR detection result to database"""
        try:
            query = """
                INSERT INTO dvr_detection_results 
                (stream_id, company_id, total_people, compliant_people, violations_count, 
                 missing_ppe, detection_confidence, detection_time, frame_timestamp, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # PostgreSQL native placeholders are already in the query
            
            dt_time = result_data.get('detection_time')
            if isinstance(dt_time, (int, float)):
                dt_time = datetime.fromtimestamp(dt_time)
                
            fr_time = result_data.get('frame_timestamp')
            if isinstance(fr_time, (int, float)):
                fr_time = datetime.fromtimestamp(fr_time)

            params = (
                result_data['stream_id'],
                result_data['company_id'],
                result_data['total_people'],
                result_data['compliant_people'],
                result_data['violations_count'],
                result_data['missing_ppe'],
                result_data['detection_confidence'],
                dt_time,
                fr_time,
                datetime.now()
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ DVR detection result saved: {result_data['stream_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add DVR detection result error: {e}")
            return False
    
    def get_dvr_detection_results(self, stream_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get DVR detection results for a stream"""
        try:
            query = """
                SELECT * FROM dvr_detection_results 
                WHERE stream_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            # PostgreSQL native placeholders
            
            result = self.execute_query(query, (stream_id, limit))
            
            if result and isinstance(result, list):
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR detection results error: {e}")
            return []
    
    def add_dvr_detection_session(self, session_data: Dict[str, Any]) -> bool:
        """Add DVR detection session to database"""
        try:
            query = """
                INSERT INTO dvr_detection_sessions 
                (session_id, dvr_id, company_id, channels, detection_mode, status, start_time, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    start_time = EXCLUDED.start_time
            """
            
            params = (
                session_data['session_id'],
                session_data['dvr_id'],
                session_data['company_id'],
                session_data['channels'],
                session_data['detection_mode'],
                session_data['status'],
                session_data['start_time'],
                datetime.now().isoformat()
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ DVR detection session saved: {session_data['session_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add DVR detection session error: {e}")
            return False
    
    def update_dvr_detection_session(self, session_id: str, update_data: Dict[str, Any]) -> bool:
        """Update DVR detection session"""
        try:
            query = """
                UPDATE dvr_detection_sessions 
                SET status = %s, end_time = %s, updated_at = %s
                WHERE session_id = %s
            """
            
            # PostgreSQL native placeholders
            
            params = (
                update_data['status'],
                update_data.get('end_time'),
                datetime.now().isoformat(),
                session_id
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ DVR detection session updated: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Update DVR detection session error: {e}")
            return False
    
    def get_dvr_detection_sessions(self, company_id: str, dvr_id: str = None) -> List[Dict[str, Any]]:
        """Get DVR detection sessions"""
        try:
            if dvr_id:
                query = """
                    SELECT * FROM dvr_detection_sessions 
                    WHERE company_id = %s AND dvr_id = %s
                    ORDER BY start_time DESC
                """
                params = (company_id, dvr_id)
            else:
                query = """
                    SELECT * FROM dvr_detection_sessions 
                    WHERE company_id = %s
                    ORDER BY start_time DESC
                """
                params = (company_id,)
            
            # PostgreSQL native placeholders
            
            result = self.execute_query(query, params)
            
            if result and isinstance(result, list):
                return result
            return []
            
        except Exception as e:
            logger.error(f"❌ Get DVR detection sessions error: {e}")
            return []
    
    # IP Camera Detection Methods
    def add_camera_detection_result(self, detection_data: Dict[str, Any]) -> bool:
        """Add IP camera detection result to database"""
        try:
            query = """
                INSERT INTO detections (
                    company_id, camera_id, detection_type, confidence,
                    people_detected, ppe_compliant, violations_count, total_people,
                    compliance_rate, compliant_people, violation_people, 
                    track_id, processing_time_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                detection_data.get('company_id'),
                detection_data.get('camera_id'),
                detection_data.get('detection_type', 'ppe'),
                detection_data.get('confidence', 0.0),
                detection_data.get('people_detected', 0),
                detection_data.get('ppe_compliant', 0),
                detection_data.get('violations_count', 0),
                detection_data.get('total_people', 0),
                detection_data.get('compliance_rate'),
                detection_data.get('compliant_people', detection_data.get('ppe_compliant', 0)),
                detection_data.get('violation_people', detection_data.get('violations_count', 0)),
                detection_data.get('track_id'),
                detection_data.get('processing_time_ms'),
            )
            
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ Camera detection result saved: {detection_data.get('camera_id')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add camera detection result error: {e}")
            return False
    
    def get_camera_detection_results(self, camera_id: str, company_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get IP camera detection results"""
        try:
            query = """
                SELECT * FROM detections
                WHERE camera_id = %s AND company_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            
            params = (camera_id, company_id, limit)
            result = self.execute_query(query, params, fetch_all=True)
            
            if result and isinstance(result, list) and len(result) > 0:
                # execute_query zaten dict döndürüyor, kontrol et
                detections = []
                for row in result:
                    if isinstance(row, dict):
                        # Zaten dict formatında
                        detection = {
                            'id': row.get('detection_id') or row.get('id'),
                            'camera_id': row.get('camera_id', camera_id),
                            'company_id': row.get('company_id', company_id),
                            'detection_type': row.get('detection_type', 'ppe'),
                            'timestamp': row.get('timestamp'),
                            'confidence': row.get('confidence', 0.0),
                            'people_detected': row.get('people_detected', 0),
                            'ppe_compliant': row.get('ppe_compliant', 0),
                            'violations_count': row.get('violations_count', 0),
                            'total_people': row.get('total_people', row.get('people_detected', 0)),
                            'compliant_people': row.get('ppe_compliant', 0),
                            'compliance_rate': row.get('compliance_rate'),
                            'processing_time_ms': row.get('processing_time_ms'),
                        }
                    else:
                        # Tuple/list formatında (fallback)
                        detection = {
                            'id': row[0] if len(row) > 0 else None,
                            'camera_id': row[1] if len(row) > 1 else camera_id,
                            'company_id': row[2] if len(row) > 2 else company_id,
                            'detection_type': row[3] if len(row) > 3 else 'ppe',
                            'timestamp': row[4] if len(row) > 4 else None,
                            'confidence': row[5] if len(row) > 5 else 0.0,
                            'people_detected': row[6] if len(row) > 6 else 0,
                            'ppe_compliant': row[7] if len(row) > 7 else 0,
                            'violations_count': row[8] if len(row) > 8 else 0,
                            'total_people': row[6] if len(row) > 6 else 0,
                            'compliant_people': row[7] if len(row) > 7 else 0
                        }
                    detections.append(detection)
                return detections
            return []
            
        except Exception as e:
            logger.error(f"❌ Get camera detection results error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_latest_camera_detection(self, camera_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get latest detection result for a camera"""
        try:
            results = self.get_camera_detection_results(camera_id, company_id, limit=1)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"❌ Get latest camera detection error: {e}")
            return None
    
    def get_camera_group_config(self, group_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get PPE configuration for a specific camera group"""
        try:
            query = "SELECT ppe_config FROM camera_groups WHERE group_id = %s AND company_id = %s"
            
            result = self.execute_query(query, (group_id, company_id), fetch_one=True)
            
            if result:
                if isinstance(result, dict):
                    ppe_config = result.get('ppe_config')
                else:
                    ppe_config = result[0]
                
                if isinstance(ppe_config, str):
                    try:
                        import json
                        return json.loads(ppe_config)
                    except:
                        return None
                return ppe_config
            return None
        except Exception as e:
            logger.error(f"❌ Get camera group config error: {e}")
            return None

    # ========================================
    # RTSP URL CACHING METHODS
    # ========================================

    def update_channel_rtsp_path(
        self,
        ip_address: str,
        channel_number: int,
        rtsp_path: str,
        company_id: str | None = None,
    ) -> bool:
        """Başarılı RTSP URL'sini dvr_channels tablosuna kaydet.
        
        Kanal henüz veritabanında yoksa oluşturur (upsert).
        
        Args:
            ip_address: DVR'ın IP adresi
            channel_number: Kanal numarası
            rtsp_path: Çalışan tam RTSP URL
            company_id: Opsiyonel şirket ID'si
            
        Returns:
            True: Başarıyla kaydedildi, False: Hata oluştu
        """
        try:
            from utils.redaction import redact_url
            
            # 1. dvr_id ve company_id'yi bul (dvr_systems üzerinden)
            if company_id:
                dvr_lookup_q = "SELECT dvr_id, company_id FROM dvr_systems WHERE ip_address = %s AND company_id = %s"
                dvr_lookup_params = (ip_address, company_id)
            else:
                dvr_lookup_q = "SELECT dvr_id, company_id FROM dvr_systems WHERE ip_address = %s"
                dvr_lookup_params = (ip_address,)

            dvr_rows = self.execute_query(dvr_lookup_q, dvr_lookup_params, fetch_all=True)
            if not dvr_rows:
                logger.debug(f"ℹ️ DVR system not found for IP {ip_address}, skipping URL cache")
                return False

            # Ambigious DVR kontrolü (company_id yoksa)
            if not company_id:
                unique_dvr_ids = {r.get('dvr_id') if isinstance(r, dict) else r[0] for r in dvr_rows}
                if len(unique_dvr_ids) != 1:
                    logger.warning(
                        f"⚠️ ambigous DVR lookup for ip={ip_address} ({len(unique_dvr_ids)} dvrs). Pass company_id."
                    )
                    return False
            
            row0 = dvr_rows[0]
            dvr_id = row0.get('dvr_id') if isinstance(row0, dict) else row0[0]
            cid_company = row0.get('company_id') if isinstance(row0, dict) else row0[1]

            if not cid_company:
                logger.error(f"❌ Could not resolve company_id for IP {ip_address}")
                return False

            # 2. UPDATE dene (Mevcut kanal varsa)
            update_query = """
                UPDATE dvr_channels dc
                SET rtsp_path = %s, updated_at = NOW()
                FROM dvr_systems ds
                WHERE dc.dvr_id = ds.dvr_id
                AND ds.ip_address = %s AND dc.channel_number = %s
            """
            affected = self.execute_query(update_query, (rtsp_path, ip_address, channel_number))
            
            if affected is not None and affected > 0:
                logger.debug(f"✅ RTSP URL updated in DB: {ip_address} ch{channel_number}")
                return True

            # 3. UPSERT dene (Update başarısızsa veya kanal yoksa)
            channel_id = f"{dvr_id}_ch{channel_number:02d}"
            name = f"Channel {channel_number}"
            http_path = f"/ch{channel_number:02d}/snapshot"
            
            upsert_query = """
                INSERT INTO dvr_channels (
                    channel_id, dvr_id, company_id, name, channel_number,
                    status, resolution_width, resolution_height, fps, rtsp_path, http_path
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (channel_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    rtsp_path = EXCLUDED.rtsp_path,
                    updated_at = NOW()
            """
            upsert_params = (
                channel_id, dvr_id, cid_company, name, channel_number,
                "active", 1920, 1080, 25, rtsp_path, http_path
            )
            
            self.execute_query(upsert_query, upsert_params)
            logger.info(f"✅ RTSP URL cached (upserted) in DB: {ip_address} ch{channel_number}")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Failed to cache RTSP URL in DB: {e}")
            return False

    def get_channel_cached_rtsp_path(
        self,
        ip_address: str,
        channel_number: int,
        *,
        company_id: str | None = None,
    ) -> Optional[str]:
        """Veritabanında kayıtlı başarılı RTSP URL'yi getir."""
        try:
            if company_id:
                query = """
                    SELECT dc.rtsp_path FROM dvr_channels dc
                    JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                    WHERE ds.ip_address = %s AND ds.company_id = %s AND dc.channel_number = %s
                    AND dc.rtsp_path IS NOT NULL AND dc.rtsp_path != ''
                """
                params = (ip_address, company_id, channel_number)
            else:
                # Ambiguous check
                dvr_rows = self.execute_query(
                    "SELECT dvr_id FROM dvr_systems WHERE ip_address = %s",
                    (ip_address,),
                    fetch_all=True,
                )
                if not dvr_rows or len(dvr_rows) > 1:
                    return None
                    
                query = """
                    SELECT dc.rtsp_path FROM dvr_channels dc
                    JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                    WHERE ds.ip_address = %s AND dc.channel_number = %s
                    AND dc.rtsp_path IS NOT NULL AND dc.rtsp_path != ''
                """
                params = (ip_address, channel_number)

            result = self.execute_query(query, params, fetch_one=True)
            if result:
                if isinstance(result, dict):
                    return result.get('rtsp_path')
                return result[0]
            return None
        except Exception as e:
            logger.debug(f"ℹ️ Could not retrieve cached RTSP URL: {e}")
            return None

    def update_camera_group_id(self, camera_id: str, company_id: str, group_id: str) -> bool:
        """Update camera's group ID"""
        try:
            query = "UPDATE cameras SET group_id = %s, updated_at = NOW() WHERE camera_id = %s AND company_id = %s"
            
            params = (group_id, camera_id, company_id)
            self.execute_query(query, params, fetch_all=False)
            logger.info(f"✅ Camera group ID updated for camera: {camera_id} to group: {group_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Update camera group ID error: {e}")
            return False

    def get_camera_by_id(self, camera_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """
        Get camera by ID and company ID
        
        Args:
            camera_id: Camera ID
            company_id: Company ID
            
        Returns:
            Camera dictionary or None if not found
        """
        try:
            query = '''
                SELECT camera_id, company_id, group_id, camera_name, location, ip_address, 
                       port, rtsp_url, username, password, protocol, stream_path,
                       auth_type, resolution, fps, quality, audio_enabled,
                       night_vision, motion_detection, recording_enabled,
                       camera_type, status, last_detection, last_test_time,
                       connection_retries, timeout, detection_zones, created_at, updated_at
                FROM cameras 
                WHERE camera_id = %s AND company_id = %s AND status != 'deleted'
            '''
            
            result = self.execute_query(query, (camera_id, company_id), fetch_one=True)
            
            if result:
                if hasattr(result, 'keys') or isinstance(result, dict):
                    return dict(result)
            return None
            
        except Exception as e:
            logger.error(f"❌ Get camera by ID error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return None

    def get_dvr_channel_by_id(self, channel_id: str, company_id: str) -> Optional[Dict[str, Any]]:
        """Get DVR channel info by ID and company ID, formatted as a camera object"""
        try:
            query = '''
                SELECT dc.channel_id, dc.company_id, NULL as group_id, dc.name as camera_name,
                       dc.channel_number as channel_number, dc.dvr_id as dvr_id,
                       CONCAT('DVR: ', ds.name) as location, ds.ip_address, ds.rtsp_port as port, 
                       dc.rtsp_path as rtsp_url, ds.username, ds.password, 'rtsp' as protocol, 
                       dc.rtsp_path as stream_path, 'basic' as auth_type, 
                       CONCAT(dc.resolution_width, 'x', dc.resolution_height) as resolution, 
                       dc.fps, 80 as quality, FALSE as audio_enabled, FALSE as night_vision, 
                       TRUE as motion_detection, TRUE as recording_enabled, 
                       'dvr_channel' as camera_type, dc.status, NULL as last_detection, 
                       dc.last_test_time, 3 as connection_retries, 10 as timeout, 
                       dc.detection_zones, dc.created_at, dc.updated_at
                FROM dvr_channels dc
                JOIN dvr_systems ds ON dc.dvr_id = ds.dvr_id
                WHERE dc.channel_id = %s AND dc.company_id = %s
            '''
            
            result = self.execute_query(query, (channel_id, company_id), fetch_one=True)
            
            if result:
                if hasattr(result, 'keys') or isinstance(result, dict):  # PostgreSQL RealDictRow
                    camera = dict(result)
                    camera['is_dvr'] = True
                    return camera
                else:
                    return None
            return None
        except Exception as e:
            logger.error(f"❌ Get dvr channel by ID error: {e}")
            return None
    
    def get_company_detection_stats(self, company_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get detection statistics for a company"""
        try:
            query = """
                SELECT 
                    COUNT(*) as total_detections,
                    SUM(people_detected) as total_people,
                    SUM(ppe_compliant) as total_compliant,
                    SUM(violations_count) as total_violations,
                    AVG(confidence) as avg_confidence
                FROM detections
                WHERE company_id = %s
                AND timestamp >= NOW() - INTERVAL '%s hours'
            """
            
            params = (company_id, hours)
            result = self.execute_query(query, params, fetch_all=True)
            
            if result and isinstance(result, list) and len(result) > 0:
                row = result[0]
                # Convert row to dict - execute_query zaten dict döndürüyor
                if isinstance(row, dict):
                    stats = {
                        'total_detections': row.get('total_detections', 0) or 0,
                        'total_people': row.get('total_people', 0) or 0,
                        'total_compliant': row.get('total_compliant', 0) or 0,
                        'total_violations': row.get('total_violations', 0) or 0,
                        'avg_confidence': float(row.get('avg_confidence', 0.0)) or 0.0
                    }
                else:
                    return {
                        'total_detections': 0,
                        'total_people': 0,
                        'total_compliant': 0,
                        'total_violations': 0,
                        'avg_confidence': 0.0,
                        'compliance_rate': 0.0
                    }
                return {
                    'total_detections': stats.get('total_detections', 0) or 0,
                    'total_people': stats.get('total_people', 0) or 0,
                    'total_compliant': stats.get('total_compliant', 0) or 0,
                    'total_violations': stats.get('total_violations', 0) or 0,
                    'avg_confidence': float(stats.get('avg_confidence', 0) or 0),
                    'compliance_rate': (stats.get('total_compliant', 0) or 0) / max(stats.get('total_people', 1) or 1, 1) * 100
                }
            return {
                'total_detections': 0,
                'total_people': 0,
                'total_compliant': 0,
                'total_violations': 0,
                'avg_confidence': 0.0,
                'compliance_rate': 0.0
            }
            
        except Exception as e:
            logger.error(f"❌ Get company detection stats error: {e}")
            return {}

    # ========================================
    # VIOLATION EVENTS METHODS
    # ========================================

    def _resolve_dvr_channel_fk(self, camera_id: str, company_id: str) -> Optional[str]:
        """
        violation_events.camera_id (örn. işlemci stream_id dvr_{dvr_id}_ch01) değerini
        dvr_channels.channel_id (genelde {dvr_id}_ch01) ile eşleştirir.
        """
        sid = str(camera_id)
        info = self.get_dvr_channel_by_id(sid, company_id)
        if info:
            pk = info.get("channel_id") or info.get("camera_id")
            if pk:
                return str(pk)
        if sid.upper().startswith("DVR_") and "_ch" in sid.lower():
            stripped = sid[4:]
            info2 = self.get_dvr_channel_by_id(stripped, company_id)
            if info2:
                pk2 = info2.get("channel_id") or info2.get("camera_id")
                if pk2:
                    return str(pk2)
                return stripped
        return None

    def _viol_events_match_camera_sql(
        self, camera_id: str, company_id: Optional[str]
    ) -> Tuple[str, Tuple[Any, ...]]:
        """
        PR3: DVR satırlarında DB camera_id NULL; stream/camera anahtarı ile arama için
        camera_id kolonu VEYA dvr_channel_id (çözülmüş channel pk) eşleşmesi.
        """
        ph = self.get_placeholder()
        dvr_pk: Optional[str] = None
        if company_id and "_ch" in str(camera_id):
            dvr_pk = self._resolve_dvr_channel_fk(camera_id, company_id)
        if dvr_pk:
            return (
                f"(camera_id = {ph} OR dvr_channel_id = {ph})",
                (camera_id, dvr_pk),
            )
        return (f"camera_id = {ph}", (camera_id,))

    def add_violation_event(self, event_data: Dict) -> bool:
        """Yeni ihlal event'i kaydet. DVR kaynağında dvr_channels eşleşmesi yoksa yazılmaz (fail-fast)."""
        try:
            camera_id = event_data['camera_id']
            company_id = event_data['company_id']

            explicit_st = event_data.get('source_type')
            explicit_dc = event_data.get('dvr_channel_id')

            if explicit_st == 'camera':
                source_type = 'camera'
                dvr_channel_id = None
            elif explicit_st == 'dvr_channel':
                if not explicit_dc or not str(explicit_dc).strip():
                    logger.error(
                        "❌ violation_events: source_type=dvr_channel but dvr_channel_id missing "
                        f"(event_id={event_data.get('event_id')}, company_id={company_id})"
                    )
                    return False
                row = self.get_dvr_channel_by_id(str(explicit_dc), company_id)
                if not row:
                    logger.error(
                        "❌ violation_events: dvr_channel_id not found in dvr_channels for company "
                        f"(event_id={event_data.get('event_id')}, dvr_channel_id={explicit_dc}, company_id={company_id})"
                    )
                    return False
                pk = row.get('channel_id') or row.get('camera_id')
                source_type = 'dvr_channel'
                dvr_channel_id = str(pk) if pk else str(explicit_dc)
            elif '_ch' in str(camera_id):
                dvr_channel_id = self._resolve_dvr_channel_fk(camera_id, company_id)
                if not dvr_channel_id:
                    logger.error(
                        "❌ violation_events: DVR camera_id could not be resolved to dvr_channels.channel_id "
                        f"(event_id={event_data.get('event_id')}, camera_id={camera_id}, company_id={company_id})"
                    )
                    return False
                source_type = 'dvr_channel'
            else:
                source_type = 'camera'
                dvr_channel_id = None

            insert_camera_id = None if source_type == 'dvr_channel' else camera_id

            query = '''
                INSERT INTO violation_events (
                    event_id, company_id, camera_id, person_id, violation_type,
                    start_time, end_time, duration_seconds, snapshot_path, severity, status,
                    source_type, dvr_channel_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''
            
            # NOTE: violation_events.start_time/end_time are stored as unix epoch (double precision)
            # in our production schema. Always write numeric seconds to avoid type mismatch.
            st = event_data.get('start_time')
            if isinstance(st, datetime):
                st = st.timestamp()
            elif isinstance(st, str):
                try:
                    st = datetime.fromisoformat(st.replace("Z", "+00:00")).timestamp()
                except Exception:
                    st = None
            elif st is not None:
                try:
                    st = float(st)
                except Exception:
                    st = None
                
            et = event_data.get('end_time')
            if isinstance(et, datetime):
                et = et.timestamp()
            elif isinstance(et, str):
                try:
                    et = datetime.fromisoformat(et.replace("Z", "+00:00")).timestamp()
                except Exception:
                    et = None
            elif et is not None:
                try:
                    et = float(et)
                except Exception:   
                    et = None

            params = (
                event_data['event_id'],
                company_id,
                insert_camera_id,
                event_data['person_id'],
                event_data['violation_type'],
                st,
                et,
                event_data.get('duration_seconds'),
                event_data.get('snapshot_path'),
                event_data.get('severity', 'warning'),
                event_data.get('status', 'active'),
                source_type,
                dvr_channel_id,
            )
            
            self.execute_query(query, params)
            logger.debug(f"✅ Violation event saved: {event_data['event_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Add violation event error: {e}")
            return False
    
    def update_violation_event(self, event_id: str, update_data: Dict) -> bool:
        """İhlal event'ini güncelle (bittiğinde)"""
        try:
            query = '''
                UPDATE violation_events 
                SET end_time = %s, duration_seconds = %s, status = %s, resolution_snapshot_path = %s
                WHERE event_id = %s
            '''
            
            et = update_data.get('end_time')
            if isinstance(et, datetime):
                et = et.timestamp()
            elif isinstance(et, str):
                try:
                    et = datetime.fromisoformat(et.replace("Z", "+00:00")).timestamp()
                except Exception:
                    et = None
            elif et is not None:
                try:
                    et = float(et)
                except Exception:
                    et = None

            params = (
                et,
                update_data.get('duration_seconds'),
                update_data.get('status', 'resolved'),
                update_data.get('resolution_snapshot_path'),
                event_id
            )
            
            self.execute_query(query, params)
            logger.debug(f"✅ Violation event updated: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Update violation event error: {e}")
            return False
    
    def get_active_violations(self, camera_id: Optional[str] = None, company_id: Optional[str] = None) -> List[Dict]:
        """Aktif ihlalleri getir - PostgreSQL Only"""
        try:
            if camera_id:
                cam_clause, cam_params = self._viol_events_match_camera_sql(
                    camera_id, company_id
                )
                query = f'''
                    SELECT * FROM violation_events 
                    WHERE {cam_clause} AND status = 'active'
                    ORDER BY start_time DESC
                '''
                params = cam_params
            elif company_id:
                query = '''
                    SELECT * FROM violation_events 
                    WHERE company_id = %s AND status = 'active'
                    ORDER BY start_time DESC
                '''
                params = (company_id,)
            else:
                query = "SELECT * FROM violation_events WHERE status = 'active' ORDER BY start_time DESC"
                params = ()
            
            results = self.execute_query(query, params, fetch_all=True)
            
            if not results or not isinstance(results, list):
                return []
            
            violations = []
            for row in results:
                if isinstance(row, dict):
                    violation = {
                        'event_id': row.get('event_id'),
                        'company_id': row.get('company_id'),
                        'camera_id': row.get('camera_id'),
                        'person_id': row.get('person_id'),
                        'violation_type': row.get('violation_type'),
                        'start_time': row.get('start_time'),
                        'end_time': row.get('end_time'),
                        'duration_seconds': row.get('duration_seconds'),
                        'snapshot_path': row.get('snapshot_path'),
                        'severity': row.get('severity'),
                        'status': row.get('status')
                    }
                    violations.append(violation)
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get active violations error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_violation_history(
        self,
        camera_id: str,
        hours: int = 24,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[Dict]:
        """İhlal geçmişini getir (DVR için company_id verilirse dvr_channel_id eşlemesi yapılır)."""
        try:
            import time
            cutoff_time = time.time() - (hours * 3600)
            cam_clause, cam_params = self._viol_events_match_camera_sql(camera_id, company_id)

            query = f'''
                SELECT * FROM violation_events 
                WHERE {cam_clause} AND start_time >= %s
                ORDER BY start_time DESC
                LIMIT %s
            '''
            
            results = self.execute_query(
                query, (*cam_params, cutoff_time, limit), fetch_all=True
            )
            
            if not results or not isinstance(results, list):
                return []
            
            violations = []
            for row in results:
                if isinstance(row, dict):
                    # Zaten dict formatında
                    violation = {
                        'event_id': row.get('event_id'),
                        'company_id': row.get('company_id'),
                        'camera_id': row.get('camera_id'),
                        'person_id': row.get('person_id'),
                        'violation_type': row.get('violation_type'),
                        'start_time': row.get('start_time'),
                        'end_time': row.get('end_time'),
                        'duration_seconds': row.get('duration_seconds'),
                        'snapshot_path': row.get('snapshot_path'),
                        'severity': row.get('severity'),
                        'status': row.get('status')
                    }
                else:
                    continue
                violations.append(violation)
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get violation history error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    # ========================================
    # PERSON VIOLATIONS METHODS
    # ========================================
    
    def update_person_violation_stats(self, person_id: str, company_id: str, violation_type: str, duration_seconds: int) -> bool:
        """Kişi ihlal istatistiklerini güncelle (Çoklu ihlal destekli)"""
        try:
            from datetime import datetime
            month = datetime.now().strftime('%Y-%m')
            
            # Çoklu ihlal desteği: Virgülle ayrılmış tipleri tek tek işle
            v_types = [v.strip() for v in violation_type.split(',')] if ',' in violation_type else [violation_type]
            
            success = True
            for v_type in v_types:
                if not v_type: continue
                
                # UPSERT kullan (PostgreSQL)
                query = '''
                    INSERT INTO person_violations (
                        person_id, company_id, month, violation_type,
                        violation_count, total_duration_seconds, last_violation_date
                    ) VALUES (%s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (person_id, company_id, month, violation_type)
                    DO UPDATE SET
                        violation_count = person_violations.violation_count + 1,
                        total_duration_seconds = person_violations.total_duration_seconds + EXCLUDED.total_duration_seconds,
                        last_violation_date = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                '''
                self.execute_query(query, (person_id, company_id, month, v_type, duration_seconds))
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Update person violation stats error: {e}")
            return False
    
    def get_person_monthly_violations(self, person_id: str, company_id: str, month: str) -> List[Dict]:
        """Kişinin aylık ihlal istatistiklerini getir"""
        try:
            query = '''
                SELECT * FROM person_violations 
                WHERE person_id = %s AND company_id = %s AND month = %s
            '''
            
            results = self.execute_query(query, (person_id, company_id, month), fetch_all=True)
            
            if not results or not isinstance(results, list):
                return []
            
            violations = []
            for row in results:
                if isinstance(row, dict):
                    # Zaten dict formatında
                    violation = {
                        'id': row.get('id'),
                        'person_id': row.get('person_id'),
                        'company_id': row.get('company_id'),
                        'month': row.get('month'),
                        'violation_type': row.get('violation_type'),
                        'violation_count': row.get('violation_count'),
                        'total_duration_seconds': row.get('total_duration_seconds'),
                        'penalty_amount': row.get('penalty_amount'),
                        'last_violation_date': row.get('last_violation_date')
                    }
                else:
                    continue
                violations.append(violation)
            
            return violations
            
        except Exception as e:
            logger.error(f"❌ Get person monthly violations error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def get_company_detection_config(self, company_id: str) -> Dict[str, Any]:
        """Single source of truth for sector + required_ppe.

        - Sector comes from `companies.sector`
        - required_ppe comes from `companies.ppe_requirements` (if configured),
          otherwise caller may fallback to sector defaults.

        UI format: [{"id":"hairnet","mandatory":true}, ...] — sadece mandatory:true olanlar;
        `mandatory:false` (ör. eldiven) pose-aware zorunlu listesine alınmaz.
        """
        try:
            query = "SELECT sector, ppe_requirements FROM companies WHERE company_id = %s"
            row = self.execute_query(query, (company_id,), fetch_one=True)
            if not row or not isinstance(row, dict):
                return {}

            sector = (row.get("sector") or "").strip()
            raw_ppe = row.get("ppe_requirements")

            required_ppe = None
            if raw_ppe is not None:
                # postgres stores JSON naturally, but handle potential string/legacy data
                if isinstance(raw_ppe, str):
                    s = raw_ppe.strip()
                    if s in ("", "null", "{}"):
                        raw_ppe = None
                    else:
                        try:
                            raw_ppe = json.loads(raw_ppe)
                        except Exception:
                            raw_ppe = None

            inner_list = None
            if isinstance(raw_ppe, dict):
                inner_list = (
                    raw_ppe.get("required_ppe")
                    or raw_ppe.get("mandatory_ppe")
                    or raw_ppe.get("mandatory")
                )
            elif isinstance(raw_ppe, list):
                inner_list = raw_ppe

            if inner_list is not None:
                required_ppe = _normalize_company_ppe_requirements_list(
                    inner_list, sector=sector or None
                )

            return {
                "sector": sector or None,
                "required_ppe": required_ppe,
            }
        except Exception:
            return {}

    # ── Active Detections State Management ──────────────────────────────────
    
    def set_detection_active(self, camera_key: str, company_id: str, camera_id: str, 
                             mode: str = 'ppe', confidence: float = 0.5, active: bool = True):
        """Kameranın algılama durumunu DB'ye kaydeder. Process'ler arası senkronizasyon için."""
        try:
            if active:
                query = """
                    INSERT INTO active_detections (camera_key, company_id, camera_id, detection_mode, confidence_threshold, status, updated_at)
                    VALUES (%s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP)
                    ON CONFLICT (camera_key) DO UPDATE SET 
                        status = TRUE, 
                        detection_mode = EXCLUDED.detection_mode,
                        confidence_threshold = EXCLUDED.confidence_threshold,
                        updated_at = CURRENT_TIMESTAMP
                """
                return self.execute_query(query, (camera_key, company_id, camera_id, mode, confidence))
            else:
                query = "DELETE FROM active_detections WHERE camera_key = %s"
                return self.execute_query(query, (camera_key,))
        except Exception as e:
            logger.error(f"❌ set_detection_active error: {e}")
            return False

    def is_detection_active(self, camera_key: str) -> bool:
        """Kameranın aktif olup olmadığını DB'den kontrol eder."""
        try:
            query = "SELECT status FROM active_detections WHERE camera_key = %s AND status = TRUE"
            res = self.execute_query(query, (camera_key,), fetch_one=True)
            return bool(res)
        except Exception as e:
            logger.error(f"❌ is_detection_active error: {e}")
            return False

    def get_active_detections_list(self, company_id: str) -> List[str]:
        """Şirkete ait aktif kamera ID listesini DB'den döner."""
        try:
            query = "SELECT camera_id FROM active_detections WHERE company_id = %s AND status = TRUE"
            rows = self.execute_query(query, (company_id,))
            if not rows:
                return []
            return [row['camera_id'] for row in rows]
        except Exception as e:
            logger.error(f"❌ get_active_detections_list error: {e}")
            return []


class CameraDiscoveryManager:
    """Keşfedilen kameraları veritabanı ile senkronize etmek için manager"""
    
    def __init__(self, db_adapter: DatabaseAdapter):
        self.db_adapter = db_adapter
        self.logger = logging.getLogger(__name__)
    
    def sync_discovered_cameras_to_db(self, company_id: str, discovered_cameras: List[Dict]) -> Dict[str, Any]:
        """
        Keşfedilen kameraları veritabanına kaydet/güncelle
        
        Args:
            company_id: Şirket ID'si
            discovered_cameras: Keşfedilen kameralar listesi
            
        Returns:
            Senkronizasyon sonucu
        """
        try:
            result = {
                'total_discovered': len(discovered_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': []
            }
            
            for camera_info in discovered_cameras:
                try:
                    # Kamera bilgilerini parse et
                    camera_data = self._parse_camera_info(camera_info)
                    
                    # Veritabanında var mı kontrol et
                    existing_camera = self._check_camera_exists(
                        company_id, 
                        camera_data['ip_address'], 
                        camera_data['port']
                    )
                    
                    if existing_camera:
                        # Güncelle
                        if self._update_camera(company_id, existing_camera['camera_id'], camera_data):
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1
                    else:
                        # Yeni kamera ekle
                        if self._add_discovered_camera(company_id, camera_data):
                            result['added'] += 1
                        else:
                            result['errors'].append(f"Failed to add camera {camera_data['name']}")
                            
                except Exception as e:
                    result['errors'].append(f"Error processing camera {camera_info.get('ip', 'unknown')}: {str(e)}")
                    self.logger.error(f"Error processing camera: {e}")
            
            self.logger.info(f"✅ Camera sync complete: {result['added']} added, {result['updated']} updated")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Camera sync failed: {e}")
            return {
                'total_discovered': len(discovered_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': [str(e)]
            }
    
    def _parse_camera_info(self, camera_info: Dict) -> Dict[str, Any]:
        """Keşfedilen kamera bilgisini parse et"""
        return {
            'name': camera_info.get('brand', 'Unknown') + f" Camera ({camera_info.get('ip', 'Unknown')})",
            'ip_address': camera_info.get('ip', ''),
            'port': camera_info.get('port', 554),
            'rtsp_url': camera_info.get('rtsp_url', ''),
            'location': f"Discovered - {camera_info.get('brand', 'Unknown')}",
            'resolution': camera_info.get('resolution', '1920x1080'),
            'fps': camera_info.get('fps', 25),
            'brand': camera_info.get('brand', 'Unknown'),
            'model': camera_info.get('model', 'Unknown')
        }
    
    def _check_camera_exists(self, company_id: str, ip_address: str, port: int) -> Optional[Dict]:
        """Kameranın veritabanında olup olmadığını kontrol et"""
        try:
            query = '''
                SELECT camera_id, camera_name, status 
                FROM cameras 
                WHERE company_id = %s AND ip_address = %s AND status = 'active'
            '''
            result = self.db_adapter.execute_query(query, (company_id, ip_address), fetch_one=True)
            
            if result:
                return {
                    'camera_id': result[0],
                    'camera_name': result[1],
                    'status': result[2]
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking camera existence: {e}")
            return None
    
    def _add_discovered_camera(self, company_id: str, camera_data: Dict) -> bool:
        """Yeni keşfedilen kamerayı veritabanına ekle"""
        try:
            import uuid
            
            # Yeni kamera ID'si oluştur
            camera_id = f"CAM_{uuid.uuid4().hex[:8].upper()}"
            
            # RTSP URL oluştur eğer yoksa
            if not camera_data['rtsp_url']:
                camera_data['rtsp_url'] = f"rtsp://{camera_data['ip_address']}:{camera_data['port']}/stream"
            
            query = '''
                INSERT INTO cameras (
                    camera_id, company_id, camera_name, location, ip_address, 
                    rtsp_url, resolution, fps, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'discovered', NOW())
            '''
            
            params = (
                camera_id,
                company_id,
                camera_data['name'],
                camera_data['location'],
                camera_data['ip_address'],
                camera_data['rtsp_url'],
                camera_data['resolution'],
                camera_data['fps']
            )
            
            self.db_adapter.execute_query(query, params)
            self.logger.info(f"✅ Added discovered camera: {camera_data['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to add discovered camera: {e}")
            return False
    
    def _update_camera(self, company_id: str, camera_id: str, camera_data: Dict) -> bool:
        """Mevcut kamerayı güncelle"""
        try:
            query = '''
                UPDATE cameras 
                SET camera_name = %s, location = %s, rtsp_url = %s, 
                    resolution = %s, fps = %s, updated_at = NOW()
                WHERE camera_id = %s AND company_id = %s
            '''
            
            params = (
                camera_data['name'],
                camera_data['location'],
                camera_data['rtsp_url'],
                camera_data['resolution'],
                camera_data['fps'],
                camera_id,
                company_id
            )
            
            self.db_adapter.execute_query(query, params)
            self.logger.info(f"✅ Updated camera: {camera_data['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update camera: {e}")
            return False
    
    def sync_config_cameras_to_db(self, company_id: str, config_cameras: Dict) -> Dict[str, Any]:
        """
        Config dosyasındaki kameraları veritabanına senkronize et
        
        Args:
            company_id: Şirket ID'si  
            config_cameras: Config dosyasındaki kameralar
            
        Returns:
            Senkronizasyon sonucu
        """
        try:
            result = {
                'total_config': len(config_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': []
            }
            
            for camera_id, config in config_cameras.items():
                try:
                    # Config'den IP ve port çıkar
                    rtsp_url = config.get('rtsp_url', '')
                    ip_address = self._extract_ip_from_rtsp(rtsp_url)
                    port = self._extract_port_from_rtsp(rtsp_url)
                    
                    camera_data = {
                        'name': config.get('name', f'Config Camera {camera_id}'),
                        'location': config.get('location', 'Unknown'),
                        'ip_address': ip_address,
                        'port': port,
                        'rtsp_url': rtsp_url,
                        'resolution': f"{config.get('resolution', [1920, 1080])[0]}x{config.get('resolution', [1920, 1080])[1]}",
                        'fps': config.get('fps', 25),
                        'enabled': config.get('enabled', True)
                    }
                    
                    # Veritabanında var mı kontrol et
                    existing_camera = self._check_camera_by_name(company_id, camera_data['name'])
                    
                    if existing_camera:
                        # Güncelle
                        if self._update_camera(company_id, existing_camera['camera_id'], camera_data):
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1
                    else:
                        # Yeni kamera ekle
                        if self._add_config_camera(company_id, camera_id, camera_data):
                            result['added'] += 1
                        else:
                            result['errors'].append(f"Failed to add config camera {camera_data['name']}")
                            
                except Exception as e:
                    result['errors'].append(f"Error processing config camera {camera_id}: {str(e)}")
                    self.logger.error(f"Error processing config camera: {e}")
            
            self.logger.info(f"✅ Config sync complete: {result['added']} added, {result['updated']} updated")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Config sync failed: {e}")
            return {
                'total_config': len(config_cameras),
                'added': 0,
                'updated': 0,
                'skipped': 0,
                'errors': [str(e)]
            }
    
    def _extract_ip_from_rtsp(self, rtsp_url: str) -> str:
        """RTSP URL'den IP adresini çıkar"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(rtsp_url)
            return parsed.hostname or ''
        except:
            return ''
    
    def _extract_port_from_rtsp(self, rtsp_url: str) -> int:
        """RTSP URL'den port'u çıkar"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(rtsp_url)
            return parsed.port or 554
        except:
            return 554
    
    def _check_camera_by_name(self, company_id: str, camera_name: str) -> Optional[Dict]:
        """Kamerayı isimle kontrol et"""
        try:
            query = '''
                SELECT camera_id, camera_name, status 
                FROM cameras 
                WHERE company_id = %s AND camera_name = %s AND status != 'deleted'
            '''
            result = self.db_adapter.execute_query(query, (company_id, camera_name), fetch_one=True)
            
            if result:
                return {
                    'camera_id': result[0],
                    'camera_name': result[1],
                    'status': result[2]
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking camera by name: {e}")
            return None
    
    def _add_config_camera(self, company_id: str, config_camera_id: str, camera_data: Dict) -> bool:
        """Config'den kamerayı veritabanına ekle"""
        try:
            import uuid
            
            # Config camera ID'sini kullan veya yeni oluştur
            camera_id = config_camera_id if config_camera_id.startswith('CAM_') else f"CAM_{uuid.uuid4().hex[:8].upper()}"
            
            query = '''
                INSERT INTO cameras (
                    camera_id, company_id, camera_name, location, ip_address, 
                    rtsp_url, resolution, fps, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW())
            '''
            
            params = (
                camera_id,
                company_id,
                camera_data['name'],
                camera_data['location'],
                camera_data['ip_address'],
                camera_data['rtsp_url'],
                camera_data['resolution'],
                camera_data['fps']
            )
            
            self.db_adapter.execute_query(query, params)
            self.logger.info(f"✅ Added config camera: {camera_data['name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to add config camera: {e}")
            return False

    def update_company_logo_url(self, company_id: str, logo_url: str) -> bool:
        """Şirket logo URL'ini güncelle"""
        try:
            print(f"🔍 Database adapter - Logo URL güncelleniyor: {company_id} -> {logo_url}")
            
            query = '''
                UPDATE companies 
                SET logo_url = %s, updated_at = NOW()
                WHERE company_id = %s
            '''
            
            print(f"🔍 Database adapter - Query: {query}")
            print(f"🔍 Database adapter - Params: ({logo_url}, {company_id})")
            
            self.db_adapter.execute_query(query, (logo_url, company_id))
            
            # Güncelleme sonrası kontrol
            print(f"🔍 Database adapter - Güncelleme sonrası kontrol...")
            check_query = "SELECT logo_url FROM companies WHERE company_id = %s"
            result = self.db_adapter.execute_query(check_query, (company_id,), fetch_one=True)
            print(f"🔍 Database adapter - Kontrol sonucu: {result}")
            
            self.logger.info(f"✅ Company logo URL updated: {company_id} -> {logo_url}")
            return True
            
        except Exception as e:
            print(f"❌ Database adapter - Logo URL güncelleme hatası: {e}")
            self.logger.error(f"❌ Failed to update company logo URL: {e}")
            return False
    
    def get_company_info(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Şirket bilgilerini getir"""
        try:
            print(f"🔍 Database adapter - get_company_info çağrıldı: {company_id}")
            
            query = '''
                SELECT company_name, sector, contact_person, email, phone, address,
                       subscription_type, subscription_start, subscription_end, max_cameras, logo_url
                FROM companies 
                WHERE company_id = %s
            '''
            
            print(f"🔍 Database adapter - Query: {query}")
            result = self.db_adapter.execute_query(query, (company_id,), fetch_one=True)
            print(f"🔍 Database adapter - Query result: {result}")
            
            if result:
                if hasattr(result, 'keys'):  # PostgreSQL RealDictRow
                    print(f"🔍 Database adapter - PostgreSQL RealDictRow formatı")
                    company_info = {
                        'company_name': result['company_name'],
                        'sector': result['sector'],
                        'contact_person': result['contact_person'],
                        'email': result['email'],
                        'phone': result['phone'],
                        'address': result['address'],
                        'subscription_type': result['subscription_type'],
                        'subscription_start': result['subscription_start'],
                        'subscription_end': result['subscription_end'],
                        'max_cameras': result['max_cameras'],
                        'logo_url': result['logo_url']
                    }
                    print(f"🔍 Database adapter - Company info: {company_info}")
                    return company_info
                else:
                    return None
            else:
                print(f"🔍 Database adapter - Query sonucu bulunamadı")
                return None
            
        except Exception as e:
            print(f"❌ Database adapter - get_company_info hatası: {e}")
            self.logger.error(f"❌ Failed to get company info: {e}")
            return None

    # ── Active Detections State Management ──────────────────────────────────
    


# ── Process-wide singletons (one PG pool per process, thread-safe) ─────────
_db_adapter_instance: Optional[DatabaseAdapter] = None
_db_adapter_lock = threading.Lock()

_camera_discovery_manager_instance: Optional[CameraDiscoveryManager] = None
_camera_discovery_manager_lock = threading.Lock()


def get_db_adapter() -> DatabaseAdapter:
    """Return the shared DatabaseAdapter (lazy init, double-checked lock)."""
    global _db_adapter_instance
    if _db_adapter_instance is None:
        with _db_adapter_lock:
            if _db_adapter_instance is None:
                _db_adapter_instance = DatabaseAdapter()
    return _db_adapter_instance


def get_camera_discovery_manager() -> CameraDiscoveryManager:
    """Return the shared CameraDiscoveryManager bound to get_db_adapter()."""
    global _camera_discovery_manager_instance
    if _camera_discovery_manager_instance is None:
        with _camera_discovery_manager_lock:
            if _camera_discovery_manager_instance is None:
                _camera_discovery_manager_instance = CameraDiscoveryManager(get_db_adapter())
    return _camera_discovery_manager_instance