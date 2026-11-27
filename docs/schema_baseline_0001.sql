--
-- PostgreSQL database dump
--

\restrict HRxcCwWPgvAKZedhVYTwknsPfNntzMs6o9RPGQu2k4G6fINXxpX5uvz3lcLoECC

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: inbound_shipment_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbound_shipment_items (
    id integer NOT NULL,
    shipment_id integer NOT NULL,
    style character varying(100) NOT NULL,
    brand character varying(60),
    warehouse_part character varying(30),
    color character varying(100),
    size character varying(50),
    line character varying(50),
    row_pos character varying(50),
    section character varying(50),
    level character varying(50),
    box_num character varying(50),
    box_count integer,
    pcs_per_box integer,
    quantity integer NOT NULL,
    expected_quantity integer,
    location character varying(200),
    notes character varying(255),
    created_at timestamp without time zone
);


--
-- Name: inbound_shipment_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.inbound_shipment_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inbound_shipment_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.inbound_shipment_items_id_seq OWNED BY public.inbound_shipment_items.id;


--
-- Name: inbound_shipments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbound_shipments (
    id integer NOT NULL,
    shipment_number character varying(100) NOT NULL,
    po_number character varying(100),
    carrier_vendor character varying(150),
    pallets_count integer NOT NULL,
    total_boxes integer NOT NULL,
    total_units integer NOT NULL,
    status character varying(50) NOT NULL,
    packing_list_filename character varying(255),
    packing_list_data text,
    commercial_invoice_filename character varying(255),
    commercial_invoice_data text,
    ai_extracted_raw text,
    notes text,
    created_by character varying(120) NOT NULL,
    approved_by character varying(120),
    approved_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: inbound_shipments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.inbound_shipments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inbound_shipments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.inbound_shipments_id_seq OWNED BY public.inbound_shipments.id;


--
-- Name: inventory_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory_items (
    id integer NOT NULL,
    style character varying(100) NOT NULL,
    brand character varying(60),
    warehouse_part character varying(30),
    placement_type character varying(30),
    color character varying(100),
    size character varying(50),
    line character varying(50),
    section character varying(50),
    level character varying(50),
    row_pos character varying(50),
    box_num character varying(50),
    location_code character varying(120),
    location character varying(200) NOT NULL,
    pcs_per_box integer,
    quantity integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: inventory_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.inventory_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inventory_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.inventory_items_id_seq OWNED BY public.inventory_items.id;


--
-- Name: stock_movements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_movements (
    id integer NOT NULL,
    item_id integer NOT NULL,
    style character varying(100) NOT NULL,
    change_amount integer NOT NULL,
    quantity_after integer NOT NULL,
    movement_type character varying(50),
    reason character varying(255),
    staff_name character varying(100),
    created_at timestamp without time zone
);


--
-- Name: stock_movements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.stock_movements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stock_movements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.stock_movements_id_seq OWNED BY public.stock_movements.id;


--
-- Name: warehouse_locations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.warehouse_locations (
    id integer NOT NULL,
    location_code character varying(120) NOT NULL,
    warehouse_part character varying(30) NOT NULL,
    zone_label character varying(100) NOT NULL,
    aisle_type character varying(20) NOT NULL,
    aisle_number character varying(30) NOT NULL,
    section character varying(50) NOT NULL,
    level character varying(30) NOT NULL,
    placement_type character varying(30) NOT NULL,
    display_location character varying(200) NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: warehouse_locations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.warehouse_locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: warehouse_locations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.warehouse_locations_id_seq OWNED BY public.warehouse_locations.id;


--
-- Name: warehouse_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.warehouse_users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(150),
    full_name character varying(120) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(50) NOT NULL,
    assigned_zone character varying(80) NOT NULL,
    is_approved integer NOT NULL,
    session_token character varying(128),
    last_seen_at timestamp without time zone,
    created_at timestamp without time zone
);


--
-- Name: warehouse_users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.warehouse_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: warehouse_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.warehouse_users_id_seq OWNED BY public.warehouse_users.id;


--
-- Name: inbound_shipment_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbound_shipment_items ALTER COLUMN id SET DEFAULT nextval('public.inbound_shipment_items_id_seq'::regclass);


--
-- Name: inbound_shipments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbound_shipments ALTER COLUMN id SET DEFAULT nextval('public.inbound_shipments_id_seq'::regclass);


--
-- Name: inventory_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_items ALTER COLUMN id SET DEFAULT nextval('public.inventory_items_id_seq'::regclass);


--
-- Name: stock_movements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_movements ALTER COLUMN id SET DEFAULT nextval('public.stock_movements_id_seq'::regclass);


--
-- Name: warehouse_locations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouse_locations ALTER COLUMN id SET DEFAULT nextval('public.warehouse_locations_id_seq'::regclass);


--
-- Name: warehouse_users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouse_users ALTER COLUMN id SET DEFAULT nextval('public.warehouse_users_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: inbound_shipment_items inbound_shipment_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbound_shipment_items
    ADD CONSTRAINT inbound_shipment_items_pkey PRIMARY KEY (id);


--
-- Name: inbound_shipments inbound_shipments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbound_shipments
    ADD CONSTRAINT inbound_shipments_pkey PRIMARY KEY (id);


--
-- Name: inventory_items inventory_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_items
    ADD CONSTRAINT inventory_items_pkey PRIMARY KEY (id);


--
-- Name: stock_movements stock_movements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_movements
    ADD CONSTRAINT stock_movements_pkey PRIMARY KEY (id);


--
-- Name: warehouse_locations warehouse_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouse_locations
    ADD CONSTRAINT warehouse_locations_pkey PRIMARY KEY (id);


--
-- Name: warehouse_users warehouse_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouse_users
    ADD CONSTRAINT warehouse_users_pkey PRIMARY KEY (id);


--
-- Name: idx_item_part_line_sec; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_item_part_line_sec ON public.inventory_items USING btree (warehouse_part, line, row_pos, section, level);


--
-- Name: idx_item_style_loc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_item_style_loc ON public.inventory_items USING btree (style, location);


--
-- Name: idx_item_style_size_color; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_item_style_size_color ON public.inventory_items USING btree (style, size, color);


--
-- Name: ix_inbound_shipment_items_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipment_items_id ON public.inbound_shipment_items USING btree (id);


--
-- Name: ix_inbound_shipment_items_shipment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipment_items_shipment_id ON public.inbound_shipment_items USING btree (shipment_id);


--
-- Name: ix_inbound_shipment_items_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipment_items_style ON public.inbound_shipment_items USING btree (style);


--
-- Name: ix_inbound_shipments_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipments_created_at ON public.inbound_shipments USING btree (created_at);


--
-- Name: ix_inbound_shipments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipments_id ON public.inbound_shipments USING btree (id);


--
-- Name: ix_inbound_shipments_po_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipments_po_number ON public.inbound_shipments USING btree (po_number);


--
-- Name: ix_inbound_shipments_shipment_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_inbound_shipments_shipment_number ON public.inbound_shipments USING btree (shipment_number);


--
-- Name: ix_inbound_shipments_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbound_shipments_status ON public.inbound_shipments USING btree (status);


--
-- Name: ix_inventory_items_brand; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_brand ON public.inventory_items USING btree (brand);


--
-- Name: ix_inventory_items_color; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_color ON public.inventory_items USING btree (color);


--
-- Name: ix_inventory_items_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_id ON public.inventory_items USING btree (id);


--
-- Name: ix_inventory_items_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_level ON public.inventory_items USING btree (level);


--
-- Name: ix_inventory_items_line; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_line ON public.inventory_items USING btree (line);


--
-- Name: ix_inventory_items_location; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_location ON public.inventory_items USING btree (location);


--
-- Name: ix_inventory_items_location_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_location_code ON public.inventory_items USING btree (location_code);


--
-- Name: ix_inventory_items_placement_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_placement_type ON public.inventory_items USING btree (placement_type);


--
-- Name: ix_inventory_items_quantity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_quantity ON public.inventory_items USING btree (quantity);


--
-- Name: ix_inventory_items_row_pos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_row_pos ON public.inventory_items USING btree (row_pos);


--
-- Name: ix_inventory_items_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_section ON public.inventory_items USING btree (section);


--
-- Name: ix_inventory_items_size; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_size ON public.inventory_items USING btree (size);


--
-- Name: ix_inventory_items_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_style ON public.inventory_items USING btree (style);


--
-- Name: ix_inventory_items_warehouse_part; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_items_warehouse_part ON public.inventory_items USING btree (warehouse_part);


--
-- Name: ix_stock_movements_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stock_movements_created_at ON public.stock_movements USING btree (created_at);


--
-- Name: ix_stock_movements_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stock_movements_id ON public.stock_movements USING btree (id);


--
-- Name: ix_stock_movements_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stock_movements_item_id ON public.stock_movements USING btree (item_id);


--
-- Name: ix_stock_movements_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stock_movements_style ON public.stock_movements USING btree (style);


--
-- Name: ix_warehouse_locations_aisle_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_aisle_number ON public.warehouse_locations USING btree (aisle_number);


--
-- Name: ix_warehouse_locations_aisle_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_aisle_type ON public.warehouse_locations USING btree (aisle_type);


--
-- Name: ix_warehouse_locations_display_location; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_display_location ON public.warehouse_locations USING btree (display_location);


--
-- Name: ix_warehouse_locations_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_id ON public.warehouse_locations USING btree (id);


--
-- Name: ix_warehouse_locations_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_level ON public.warehouse_locations USING btree (level);


--
-- Name: ix_warehouse_locations_location_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_warehouse_locations_location_code ON public.warehouse_locations USING btree (location_code);


--
-- Name: ix_warehouse_locations_placement_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_placement_type ON public.warehouse_locations USING btree (placement_type);


--
-- Name: ix_warehouse_locations_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_section ON public.warehouse_locations USING btree (section);


--
-- Name: ix_warehouse_locations_warehouse_part; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_locations_warehouse_part ON public.warehouse_locations USING btree (warehouse_part);


--
-- Name: ix_warehouse_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_warehouse_users_email ON public.warehouse_users USING btree (email);


--
-- Name: ix_warehouse_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_users_id ON public.warehouse_users USING btree (id);


--
-- Name: ix_warehouse_users_is_approved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_users_is_approved ON public.warehouse_users USING btree (is_approved);


--
-- Name: ix_warehouse_users_session_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_users_session_token ON public.warehouse_users USING btree (session_token);


--
-- Name: ix_warehouse_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_warehouse_users_username ON public.warehouse_users USING btree (username);


--
-- Name: inbound_shipment_items inbound_shipment_items_shipment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbound_shipment_items
    ADD CONSTRAINT inbound_shipment_items_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES public.inbound_shipments(id) ON DELETE CASCADE;


--
-- Name: stock_movements stock_movements_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_movements
    ADD CONSTRAINT stock_movements_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.inventory_items(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict HRxcCwWPgvAKZedhVYTwknsPfNntzMs6o9RPGQu2k4G6fINXxpX5uvz3lcLoECC

